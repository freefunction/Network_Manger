import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import networkx as nx
import numpy as np
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
import json
from io import BytesIO
import math
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import networkx as nx
from math import ceil


# Définitions des types de trafic
class TrafficType(Enum):
    G100 = "100G"
    G10 = "10G"
    G1 = "1G"
    
    @property
    def capacity_gbps(self):
        return {"100G": 100, "10G": 10, "1G": 1}[self.value]

# Types de cartes OCH
class CardType(Enum):
    OCH_200 = "OCH-200"
    OCH_400 = "OCH-400"
    
    @property
    def capacity_gbps(self):
        return {"OCH-200": 19200, "OCH-400": 25600}[self.value]
    
    @property
    def cost(self):
        return {"OCH-200": 10000, "OCH-400": 15000}[self.value]

@dataclass
class OCHCard:
    card_type: CardType
    location: str
    capacity_gbps: float
    cost: float
    used_capacity_gbps: float = 0.0
    
    @property
    def available_capacity_gbps(self) -> float:
        return max(0.0, self.capacity_gbps - self.used_capacity_gbps)

    def can_accommodate(self, bandwidth_gbps: float) -> bool:
        return self.available_capacity_gbps >= bandwidth_gbps
from typing import List, Dict, Optional
import math

@dataclass
class Route:
    path: List[str]
    traffic: Dict[TrafficType, int] = None
    manager: Optional['OpticalNetworkManager'] = None

    def __post_init__(self):
        self.traffic = self.traffic or {t: 0 for t in TrafficType}
        self.cards: Dict[str, List[OCHCard]] = {}
        self._initialize_cards()


    def _get_card_specs(self):
        """Return (och200_capacity, och400_capacity, och200_cost, och400_cost)."""
        if self.manager and getattr(self.manager, "config", None):
            cfg = self.manager.config
            och200 = cfg['och_cards']['OCH-200']
            och400 = cfg['och_cards']['OCH-400']
            och200_capacity = och200['channels'] * och200['capacity_per_channel']
            och400_capacity = och400['channels'] * och400['capacity_per_channel']
            och200_cost = och200['cost']
            och400_cost = och400['cost']
        else:
            och200_capacity = 96 * 200
            och400_capacity = 64 * 400
            och200_cost = 10000
            och400_cost = 15000
        return och200_capacity, och400_capacity, och200_cost, och400_cost

    def _initialize_cards(self):
        """Initialize OCH cards based on traffic and manager configuration."""
        if not self.path:
            return

        total_bandwidth = self.get_total_bandwidth_gbps()
        och200_capacity, och400_capacity, och200_cost, och400_cost = self._get_card_specs()

        # Choose base type
        if total_bandwidth <= och200_capacity:
            base_card_type = CardType.OCH_200
            base_capacity = och200_capacity
            base_cost = och200_cost
        else:
            base_card_type = CardType.OCH_400
            base_capacity = och400_capacity
            base_cost = och400_cost

        cards_needed_per_location = max(1, math.ceil(total_bandwidth / base_capacity))

        # Nested helper
        def create_cards_for_location(loc: str):
            self.cards[loc] = []
            remaining = total_bandwidth
            for _ in range(cards_needed_per_location):
                used = min(base_capacity, remaining)
                remaining -= used
                card = OCHCard(
                    card_type=base_card_type,
                    location=loc,
                    capacity_gbps=base_capacity,
                    cost=base_cost,
                    used_capacity_gbps=used
                )
                self.cards[loc].append(card)

        # Create for source
        create_cards_for_location(self.path[0])
        # Create for destination if different
        if len(self.path) > 1 and self.path[-1] != self.path[0]:
            create_cards_for_location(self.path[-1])

    def get_total_bandwidth_gbps(self) -> float:
        """Compute total bandwidth used, taking traffic efficiency into account."""
        total = 0
        for traffic_type, count in self.traffic.items():
            bw = traffic_type.capacity_gbps
            eff = 1.0
            if self.manager and getattr(self.manager, "config", None):
                eff_cfg = self.manager.config.get('traffic_efficiency', {})
                if traffic_type == TrafficType.G1:
                    eff = eff_cfg.get('1G', 1.0)
                elif traffic_type == TrafficType.G10:
                    eff = eff_cfg.get('10G', 1.0)
                elif traffic_type == TrafficType.G100:
                    eff = eff_cfg.get('100G', 1.0)
            total += bw * count * eff
        return total

    def get_total_capacity_gbps(self) -> float:
        return sum(card.capacity_gbps for cards in self.cards.values() for card in cards)

    def get_utilization_percent(self) -> float:
        capacity = self.get_total_capacity_gbps()
        if capacity <= 0:
            return 0.0
        return self.get_total_bandwidth_gbps() / capacity * 100.0

    def can_accommodate_traffic(self, traffic_type: TrafficType, amount: int) -> bool:
        additional_bw = traffic_type.capacity_gbps * amount
        return self.get_total_bandwidth_gbps() + additional_bw <= self.get_total_capacity_gbps()

    def can_accommodate_combined_traffic(self, combined_traffic: Dict[TrafficType, int]) -> bool:
        additional_bw = sum(t.capacity_gbps * amt for t, amt in combined_traffic.items())
        return self.get_total_bandwidth_gbps() + additional_bw <= self.get_total_capacity_gbps()

    def add_traffic(self, traffic_type: TrafficType, amount: int) -> bool:
        if self.can_accommodate_traffic(traffic_type, amount):
            self.traffic[traffic_type] += amount
            self._update_card_usage()
            return True
        return False

    def add_combined_traffic(self, combined_traffic: Dict[TrafficType, int]) -> bool:
        if self.can_accommodate_combined_traffic(combined_traffic):
            for t, amt in combined_traffic.items():
                self.traffic[t] += amt
            self._update_card_usage()
            return True
        return False

    def _update_card_usage(self):
        """Distribute total bandwidth across all cards proportionally."""
        total_bw = self.get_total_bandwidth_gbps()
        all_cards = [card for cards in self.cards.values() for card in cards]
        if not all_cards:
            return
        remaining = total_bw
        for card in all_cards:
            card.used_capacity_gbps = min(card.capacity_gbps, remaining)
            remaining -= card.used_capacity_gbps

# Assuming these exist elsewhere:
# from your_module import Route, TrafficType, CardType, OCHCard

@dataclass
class InjectionOption:
    option_type: str  # "EXISTING", "NEW", "MODIFY"
    path: List[str]
    cost: float
    cards_needed: int
    converters_needed: int
    description: str
    route_id: str = None  # For existing routes
    utilization_after: float = 0


class OpticalNetworkManager:
    
    def __init__(self):
        self.routes: Dict[str, 'Route'] = {}
        self.graph = nx.Graph()
        self.node_routes: Dict[str, List[str]] = {}
        # Default configuration
        self.config = {
            'och_cards': {
                'OCH-200': {'channels': 96, 'capacity_per_channel': 200, 'cost': 10000},
                'OCH-400': {'channels': 64, 'capacity_per_channel': 400, 'cost': 15000},
            },
            'converter_cost': 500,
            'traffic_efficiency': {
                '1G': 0.1,
                '10G': 0.1,
                '100G': 0.5
            }
        }

    def load_routes_from_data(self, data: List[Tuple[str, int, int, int]]):
        """Load routes from raw data."""
        self.routes.clear()
        self.graph.clear()
        self.node_routes.clear()

        for route_path, traffic_100g, traffic_10g, traffic_1g in data:
            path = [node.strip() for node in route_path.split('|')]
            traffic = {
                TrafficType.G100: traffic_100g,
                TrafficType.G10: traffic_10g,
                TrafficType.G1: traffic_1g
            }
            route = Route(path, traffic, manager=self)
            route_id = route_path
            self.routes[route_id] = route

            # Update graph and node_routes
            for i in range(len(path) - 1):
                self.graph.add_edge(path[i], path[i + 1])
            for node in path:
                self.node_routes.setdefault(node, []).append(route_id)

    def find_combined_injection_options(self, source: str, destination: str, 
                                       combined_traffic: Dict['TrafficType', int]) -> List[InjectionOption]:
        """Find injection options for combined traffic."""
        options: List[InjectionOption] = []

        total_bandwidth_needed = sum(ttype.capacity_gbps * amount for ttype, amount in combined_traffic.items())

        # Existing routes
        options.extend(self._find_existing_combined_options(source, destination, combined_traffic, total_bandwidth_needed))
        # New direct route
        new_option = self._find_new_combined_route_option(source, destination, combined_traffic, total_bandwidth_needed)
        if new_option:
            options.append(new_option)
        # Modify existing routes
        options.extend(self._find_modify_combined_options(source, destination, combined_traffic, total_bandwidth_needed))

        # Sort by cost
        options.sort(key=lambda x: x.cost)
        return options

    def _find_existing_combined_options(self, source: str, destination: str, 
                                      combined_traffic: Dict['TrafficType', int], 
                                      total_bandwidth_needed: float) -> List[InjectionOption]:
        options: List[InjectionOption] = []

        for route_id, route in self.routes.items():
            if len(route.path) >= 2 and route.path[0] == source and route.path[-1] == destination:
                if route.can_accommodate_combined_traffic(combined_traffic):
                    current_bandwidth = route.get_total_bandwidth_gbps()
                    utilization_after = ((current_bandwidth + total_bandwidth_needed) / route.get_total_capacity_gbps()) * 100

                    traffic_desc = [f"{amount}x {ttype.value}" for ttype, amount in combined_traffic.items()]
                    options.append(
                        InjectionOption(
                            option_type="EXISTING",
                            path=route.path.copy(),
                            cost=0,
                            cards_needed=0,
                            converters_needed=0,
                            description=f"Use existing route for {', '.join(traffic_desc)}: {' → '.join(route.path)}",
                            route_id=route_id,
                            utilization_after=utilization_after
                        )
                    )
        return options

    def _find_new_combined_route_option(self, source: str, destination: str, 
                                   combined_traffic: Dict[TrafficType, int], 
                                   total_bandwidth_needed: float) -> Optional[InjectionOption]:
        """Crée une option pour une nouvelle route directe avec trafic combiné"""
        if source == destination:
            return None

        och200 = self.config['och_cards']['OCH-200']
        och400 = self.config['och_cards']['OCH-400']

        och200_capacity = och200['channels'] * och200['capacity_per_channel']
        och400_capacity = och400['channels'] * och400['capacity_per_channel']
        och200_cost = och200['cost']
        och400_cost = och400['cost']

        if total_bandwidth_needed <= och200_capacity:
            card_type = CardType.OCH_200
            card_cost = och200_cost
        else:
            card_type = CardType.OCH_400
            card_cost = och400_cost

        cost = 2 * card_cost  # two cards: source + destination
        path = [source, destination]

        traffic_desc = [f"{amount}x {ttype.value}" for ttype, amount in combined_traffic.items()]

        return InjectionOption(
            option_type="NEW",
            path=path,
            cost=cost,
            cards_needed=2,
            converters_needed=0,
            description=f"Créer nouvelle route directe pour {', '.join(traffic_desc)}: {' → '.join(path)} avec cartes {card_type.value}",
            utilization_after=(total_bandwidth_needed / (och200_capacity if card_type == CardType.OCH_200 else och400_capacity)) * 100
        )


    def _find_modify_combined_options(self, source: str, destination: str, 
                                    combined_traffic: Dict[TrafficType, int], 
                                    total_bandwidth_needed: float) -> List[InjectionOption]:
        """Trouve les options de modification de routes existantes pour trafic combiné"""
        options = []

        for route_id, route in self.routes.items():
            try:
                source_idx = route.path.index(source)
                dest_idx = route.path.index(destination)
            except ValueError:
                continue

            if source_idx >= dest_idx:
                continue

            if source_idx == 0 and dest_idx == len(route.path) - 1:
                continue

            total_bandwidth = route.get_total_bandwidth_gbps() + total_bandwidth_needed

            och200 = self.config['och_cards']['OCH-200']
            och400 = self.config['och_cards']['OCH-400']

            och200_capacity = och200['channels'] * och200['capacity_per_channel']
            och400_capacity = och400['channels'] * och400['capacity_per_channel']
            och200_cost = och200['cost']
            och400_cost = och400['cost']

            if total_bandwidth <= och200_capacity:
                card_type = CardType.OCH_200
                card_cost = och200_cost
                card_capacity = och200_capacity
            else:
                card_type = CardType.OCH_400
                card_cost = och400_cost
                card_capacity = och400_capacity

            converter_cost = self.config.get('converter_cost', 500)
            cost = 2 * card_cost + converter_cost

            modified_path = route.path[source_idx:dest_idx + 1]

            traffic_desc = [f"{amount}x {ttype.value}" for ttype, amount in combined_traffic.items()]

            option = InjectionOption(
                option_type="MODIFY",
                path=modified_path,
                cost=cost,
                cards_needed=2,
                converters_needed=1,
                description=f"Modifier route {route_id} pour {', '.join(traffic_desc)}: injection entre {source} et {destination}",
                route_id=route_id,
                utilization_after=(total_bandwidth / card_capacity) * 100
            )
            options.append(option)

        return options



    def apply_combined_injection(self, option: InjectionOption, combined_traffic: Dict['TrafficType', int]) -> bool:
        try:
            if option.option_type == "EXISTING" or option.option_type == "MODIFY":
                route = self.routes[option.route_id]
                return route.add_combined_traffic(combined_traffic)

            elif option.option_type == "NEW":
                new_traffic = {t: 0 for t in TrafficType}
                for ttype, amount in combined_traffic.items():
                    new_traffic[ttype] = amount
                new_route = Route(option.path, new_traffic, manager=self)

                traffic_parts = [f"{amount}x{ttype.value}" for ttype, amount in combined_traffic.items() if amount > 0]
                new_route_id = f"{option.path[0]}→{option.path[-1]}_{'_'.join(traffic_parts)}"
                self.routes[new_route_id] = new_route

                for i in range(len(option.path) - 1):
                    self.graph.add_edge(option.path[i], option.path[i + 1])
                for node in option.path:
                    self.node_routes.setdefault(node, []).append(new_route_id)
                return True

        except Exception as e:
            print(f"Error applying combined injection: {e}")
            return False
        return False

    def get_network_summary(self) -> dict:
        total_traffic = {TrafficType.G100: 0, TrafficType.G10: 0, TrafficType.G1: 0}
        total_bandwidth_used = 0
        total_bandwidth_capacity = 0
        card_stats = {'OCH-200': 0, 'OCH-400': 0}
        route_utilizations = []

        for route in self.routes.values():
            for ttype in TrafficType:
                total_traffic[ttype] += route.traffic.get(ttype, 0)
            route_bandwidth = route.get_total_bandwidth_gbps()
            route_capacity = route.get_total_capacity_gbps()
            utilization = route.get_utilization_percent()

            total_bandwidth_used += route_bandwidth
            total_bandwidth_capacity += route_capacity
            route_utilizations.append(utilization)

            for cards_list in route.cards.values():
                for card in cards_list:
                    card_stats[card.card_type.value] += 1

        overall_utilization = (total_bandwidth_used / total_bandwidth_capacity * 100) if total_bandwidth_capacity > 0 else 0
        utilization_by_traffic = {}
        for ttype in TrafficType:
            traffic_bandwidth = total_traffic[ttype] * ttype.capacity_gbps
            utilization_by_traffic[ttype.value] = (traffic_bandwidth / total_bandwidth_capacity * 100) if total_bandwidth_capacity > 0 else 0

        return {
            'total_routes': len(self.routes),
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'total_traffic': {t.value: v for t, v in total_traffic.items()},
            'total_bandwidth_used_gbps': total_bandwidth_used,
            'total_bandwidth_capacity_gbps': total_bandwidth_capacity,
            'overall_utilization_percent': round(overall_utilization, 1),
            'utilization': utilization_by_traffic,
            'card_statistics': card_stats,
            'average_route_utilization': round(sum(route_utilizations) / len(route_utilizations), 1) if route_utilizations else 0,
            'max_route_utilization': round(max(route_utilizations), 1) if route_utilizations else 0
        }

# Interface Streamlit
def init_session_state():
    """Initialize session state variables"""
    if 'manager' not in st.session_state:
        st.session_state.manager = OpticalNetworkManager()
    if 'routes_loaded' not in st.session_state:
        st.session_state.routes_loaded = False
    if 'simulation_history' not in st.session_state:
        st.session_state.simulation_history = []

def create_network_graph(manager: OpticalNetworkManager):
    """Create interactive network visualization using plotly"""
    if not manager.routes:
        return None
    
    # Create graph layout
    pos = nx.spring_layout(manager.graph, k=3, iterations=50)
    
    # Extract edges and nodes
    edge_x, edge_y = [], []
    
    for edge in manager.graph.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    
    # Node information
    node_x, node_y, node_text, node_size, node_color = [], [], [], [], []
    
    for node in manager.graph.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        
        # Count routes passing through this node
        route_count = len(manager.node_routes.get(node, []))
        node_text.append(f"{node}<br>Routes: {route_count}")
        node_size.append(max(20, route_count * 5))
        node_color.append(route_count)
    
    # Create plotly figure
    fig = go.Figure()
    
    # Add edges
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=2, color='#888'),
        hoverinfo='none',
        mode='lines',
        name='Connections'
    ))
    
    # Add nodes
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        hovertext=node_text,
        text=[node for node in manager.graph.nodes()],
        textposition="middle center",
        marker=dict(
            showscale=True,
            colorscale='Viridis',
            color=node_color,
            size=node_size,
            colorbar=dict(
                thickness=15,
                len=0.5,
                x=1.02,
                title="Route Count"
            ),
            line=dict(width=2, color='white')
        ),
        name='Nodes'
    ))
    
    fig.update_layout(
        title=dict(text="Network Topology", font=dict(size=16)),
        showlegend=False,
        hovermode='closest',
        margin=dict(b=20,l=5,r=5,t=40),
        annotations=[dict(
            text="Hover over nodes for details",
            showarrow=False,
            xref="paper", yref="paper",
            x=0.005, y=-0.002,
            xanchor='left', yanchor='bottom',
            font=dict(color="#888", size=12)
        )],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='rgba(0,0,0,0)',
        height=500
    )
    
    return fig

def simulate_injection_ui():
    """UI pour la simulation d'injection de trafic combiné"""
    st.subheader("🚀 Traffic Injection Simulation")
    
    manager = st.session_state.manager
    
    if not manager.routes:
        st.warning("Please load routes first!")
        return
    
    # Get all nodes
    nodes = sorted(list(manager.graph.nodes()))
    
    col1, col2 = st.columns(2)
    
    with col1:
        source = st.selectbox("Source Node", nodes, key="sim_source")
    
    with col2:
        destination = st.selectbox("Destination Node", 
                                 [n for n in nodes if n != source], 
                                 key="sim_destination")
    
    # Section pour le trafic combiné
    st.markdown("**Traffic to Inject:**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        traffic_100g = st.number_input("100G Connections", min_value=0, value=0, key="sim_100g")
    
    with col2:
        traffic_10g = st.number_input("10G Connections", min_value=0, value=0, key="sim_10g")
    
    with col3:
        traffic_1g = st.number_input("1G Connections", min_value=0, value=0, key="sim_1g")
    
    total_traffic = traffic_100g + traffic_10g + traffic_1g
    
    if total_traffic == 0:
        st.warning("Please specify at least one type of traffic to inject.")
        return
    
    if st.button("🔍 Find Injection Options", type="primary"):
        # Create combined traffic request
        combined_traffic = {}
        if traffic_100g > 0:
            combined_traffic[TrafficType.G100] = traffic_100g
        if traffic_10g > 0:
            combined_traffic[TrafficType.G10] = traffic_10g
        if traffic_1g > 0:
            combined_traffic[TrafficType.G1] = traffic_1g
        
        # Find options for combined traffic
        options = manager.find_combined_injection_options(source, destination, combined_traffic)
        
        if options:
            st.success(f"Found {len(options)} options for combined traffic from {source} to {destination}")
            
            # Display combined traffic summary
            traffic_summary = []
            total_bandwidth = 0
            for traffic_type, amount in combined_traffic.items():
                traffic_summary.append(f"{amount}x {traffic_type.value}")
                total_bandwidth += traffic_type.capacity_gbps * amount
            
            st.info(f"**Traffic Request:** {', '.join(traffic_summary)} (Total: {total_bandwidth} Gbps)")
            
            for i, option in enumerate(options[:5], 1):  # Show top 5 options
                with st.expander(f"🎯 Option {i}: {option.option_type.upper()} - Cost: €{option.cost:,.0f}"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Cards Needed", option.cards_needed)
                    with col2:
                        st.metric("Converters Needed", option.converters_needed)
                    with col3:
                        st.metric("Total Cost", f"€{option.cost:,.0f}")
                    with col4:
                        st.metric("Utilization After", f"{option.utilization_after:.1f}%")
                    
                    st.write(f"**Path:** {' → '.join(option.path)}")
                    st.write(f"**Description:** {option.description}")
                    
                    # Traffic breakdown
                    st.write("**Traffic Details:**")
                    for traffic_type, amount in combined_traffic.items():
                        bandwidth = traffic_type.capacity_gbps * amount
                        st.write(f"• {amount}x {traffic_type.value}: {bandwidth} Gbps")
                    st.write(f"• **Total:** {total_bandwidth} Gbps")
                    
                    # Indicateur de couleur selon l'utilisation
                    if option.utilization_after > 90:
                        st.error("⚠️ High utilization - consider upgrading cards")
                    elif option.utilization_after > 70:
                        st.warning("⚠️ Medium utilization")
                    else:
                        st.success("✅ Good utilization level")
                    
                    if st.button(f"Apply Option {i}", key=f"apply_combined_{i}"):
                        success = manager.apply_combined_injection(option, combined_traffic)
                        if success:
                            st.success("✅ Combined option applied successfully!")
                            st.session_state.simulation_history.append({
                                'source': source,
                                'destination': destination,
                                'traffic_100g': traffic_100g,
                                'traffic_10g': traffic_10g,
                                'traffic_1g': traffic_1g,
                                'option_type': option.option_type,
                                'cost': option.cost,
                                'timestamp': pd.Timestamp.now()
                            })
                            st.rerun()
                        else:
                            st.error("❌ Failed to apply option")
        else:
            st.error("No viable options found for this combined traffic injection request")


def configuration_panel(manager) -> dict:
    """Configuration panel for OCH network parameters with persistent values."""
    st.subheader("⚙️ OCH Network Configuration")

    # Initialize session_state values only if they don't exist
    if "och200_channels" not in st.session_state:
        st.session_state.och200_channels = manager.config['och_cards']['OCH-200']['channels']
    if "och200_capacity" not in st.session_state:
        st.session_state.och200_capacity = manager.config['och_cards']['OCH-200']['capacity_per_channel']
    if "och200_cost" not in st.session_state:
        st.session_state.och200_cost = manager.config['och_cards']['OCH-200']['cost']
    if "och400_channels" not in st.session_state:
        st.session_state.och400_channels = manager.config['och_cards']['OCH-400']['channels']
    if "och400_capacity" not in st.session_state:
        st.session_state.och400_capacity = manager.config['och_cards']['OCH-400']['capacity_per_channel']
    if "och400_cost" not in st.session_state:
        st.session_state.och400_cost = manager.config['och_cards']['OCH-400']['cost']
    if "converter_cost" not in st.session_state:
        st.session_state.converter_cost = manager.config.get('converter_cost', 500)
    if "g1_efficiency" not in st.session_state:
        st.session_state.g1_efficiency = manager.config['traffic_efficiency'].get('1G', 0.1)
    if "g10_efficiency" not in st.session_state:
        st.session_state.g10_efficiency = manager.config['traffic_efficiency'].get('10G', 0.1)
    if "g100_efficiency" not in st.session_state:
        st.session_state.g100_efficiency = manager.config['traffic_efficiency'].get('100G', 0.5)

    # --- OCH Card Settings ---
    with st.expander("OCH Card Settings"):
        st.write("Configure OCH card specifications:")
        col1, col2 = st.columns(2)

        with col1:
            st.write("**OCH-200 Card:**")
            och200_channels = st.number_input(
                "Max Channels",
                min_value=1,
                value=st.session_state.och200_channels,
                key="och200_channels"
            )
            och200_capacity = st.number_input(
                "Channel Capacity (Gbps)",
                min_value=1,
                value=st.session_state.och200_capacity,
                key="och200_capacity"
            )
            st.metric("Total OCH-200 Capacity", f"{och200_channels * och200_capacity} Gbps")

        with col2:
            st.write("**OCH-400 Card:**")
            och400_channels = st.number_input(
                "Max Channels",
                min_value=1,
                value=st.session_state.och400_channels,
                key="och400_channels"
            )
            och400_capacity = st.number_input(
                "Channel Capacity (Gbps)",
                min_value=1,
                value=st.session_state.och400_capacity,
                key="och400_capacity"
            )
            st.metric("Total OCH-400 Capacity", f"{och400_channels * och400_capacity} Gbps")

    # --- Cost Parameters ---
    with st.expander("Cost Parameters"):
        st.write("Configure costs for network modifications:")
        col1, col2, col3 = st.columns(3)
        with col1:
            och200_cost = st.number_input(
                "OCH-200 Card Cost (€)",
                min_value=0,
                value=st.session_state.och200_cost,
                key="och200_cost"
            )
        with col2:
            och400_cost = st.number_input(
                "OCH-400 Card Cost (€)",
                min_value=0,
                value=st.session_state.och400_cost,
                key="och400_cost"
            )
        with col3:
            converter_cost = st.number_input(
                "Converter Cost (€)",
                min_value=0,
                value=st.session_state.converter_cost,
                key="converter_cost"
            )

    # --- Traffic Efficiency ---
    with st.expander("Traffic Efficiency Settings"):
        st.write("Configure how traffic types map to OCH channels:")
        col1, col2, col3 = st.columns(3)
        with col1:
            g1_efficiency = st.slider(
                "1G Efficiency",
                0.1,
                1.0,
                value=st.session_state.g1_efficiency,
                key="g1_efficiency"
            )
        with col2:
            g10_efficiency = st.slider(
                "10G Efficiency",
                0.1,
                1.0,
                value=st.session_state.g10_efficiency,
                key="g10_efficiency"
            )
        with col3:
            g100_efficiency = st.slider(
                "100G Efficiency",
                0.1,
                1.0,
                value=st.session_state.g100_efficiency,
                key="g100_efficiency"
            )

    # --- Apply Button ---
    if st.button("✅ Apply Configuration"):
        # Update manager.config
        manager.config = {
            'och_cards': {
                'OCH-200': {'channels': och200_channels, 'capacity_per_channel': och200_capacity, 'cost': och200_cost},
                'OCH-400': {'channels': och400_channels, 'capacity_per_channel': och400_capacity, 'cost': och400_cost}
            },
            'converter_cost': converter_cost,
            'traffic_efficiency': {'1G': g1_efficiency, '10G': g10_efficiency, '100G': g100_efficiency}
        }

        # Re-initialize all routes with updated config
        for route in manager.routes.values():
            route.manager = manager
            route._initialize_cards()

        st.success("Configuration applied successfully!")

    # Return the current config (based on widget values)
    return {
        'och_cards': {
            'OCH-200': {'channels': och200_channels, 'capacity_per_channel': och200_capacity, 'cost': och200_cost},
            'OCH-400': {'channels': och400_channels, 'capacity_per_channel': och400_capacity, 'cost': och400_cost}
        },
        'converter_cost': converter_cost,
        'traffic_efficiency': {'1G': g1_efficiency, '10G': g10_efficiency, '100G': g100_efficiency}
    }



def main():
    # Check if running with streamlit
    try:
        st.set_page_config(
            page_title="Optical Network Manager",
            page_icon="🌐",
            layout="wide",
            initial_sidebar_state="expanded"
        )
    except Exception as e:
        print("⚠️  Please run this application using: streamlit run optical_manager_corrected.py")
        return
    
    # Initialize session state
    init_session_state()
    
    # Header
    st.title("🌐 Optical Network Transmission Manager")
    st.markdown("*Advanced network simulation and traffic injection optimization*")
    
    # Sidebar
    with st.sidebar:
        st.header("📊 Navigation")
        
        page = st.selectbox("Choose a page:", [
            "🏠 Dashboard",
            "📁 Data Management", 
            "🚀 Simulation",
            "⚙️ Configuration",
            "📈 Analytics"
        ])
        
        st.markdown("---")
        
        # Quick stats
        if st.session_state.routes_loaded:
            manager = st.session_state.manager
            summary = manager.get_network_summary()
            
            st.metric("Total Routes", summary['total_routes'])
            st.metric("Network Nodes", summary['total_nodes'])
            st.metric("Connections", summary['total_edges'])
            
            st.markdown("**OCH Utilization:**")
            overall_util = summary.get('overall_utilization_percent', 0)
            st.progress(min(overall_util/100, 1.0), f"Overall: {overall_util:.1f}%")
            
            st.markdown("**Traffic Summary:**")
            for traffic_type, amount in summary['total_traffic'].items():
                if amount > 0:
                    st.write(f"• {traffic_type}: {amount} connections")
    
    # Main content based on selected page
    if page == "🏠 Dashboard":
        if not st.session_state.routes_loaded:
            st.info("👆 Please load your route data first in the 'Data Management' section")
        else:
            manager = st.session_state.manager
            
            # Network overview
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader("🗺️ Network Topology")
                network_fig = create_network_graph(manager)
                if network_fig:
                    st.plotly_chart(network_fig, use_container_width=True)
            
            with col2:
                st.subheader("📊 Quick Stats")
                summary = manager.get_network_summary()
                
                st.metric("Total Bandwidth Used", f"{summary['total_bandwidth_used_gbps']:,.0f} Gbps")
                st.metric("Total Capacity", f"{summary['total_bandwidth_capacity_gbps']:,.0f} Gbps")
                st.metric("Overall Utilization", f"{summary['overall_utilization_percent']:.1f}%")
                
                st.markdown("**Card Distribution:**")
                for card_type, count in summary['card_statistics'].items():
                    st.write(f"• {card_type}: {count} cards")
                
                st.markdown("**Traffic by Type:**")
                for traffic_type, amount in summary['total_traffic'].items():
                    if amount > 0:
                        st.write(f"• {traffic_type}: {amount} connections")
    
    elif page == "📁 Data Management":
        st.subheader("📁 Data Management")
        
        tab1, tab2, tab3 = st.tabs(["📤 Upload Data", "👀 View Routes", "💾 Export"])
        
        with tab1:
            st.write("Upload your route data:")
            
            # File upload
            uploaded_file = st.file_uploader(
                "Choose Excel file (route_existant.xlsx)", 
                type=['xlsx', 'xls'],
                help="Excel file should contain columns: Route, 100G, 10G, 1G"
            )
            
            if uploaded_file:
                try:
                    df = pd.read_excel(uploaded_file)
                    st.write("Preview of uploaded data:")
                    st.dataframe(df.head())
                    
                    if st.button("Load Routes", type="primary"):
                        # Load using pandas and convert to manager format
                        data_tuples = []
                        for _, row in df.iterrows():
                            data_tuples.append((
                                str(row['Route']),
                                int(row['100G'] if pd.notna(row['100G']) else 0),
                                int(row['10G'] if pd.notna(row['10G']) else 0),
                                int(row['1G'] if pd.notna(row['1G']) else 0)
                            ))
                        
                        st.session_state.manager = OpticalNetworkManager()
                        st.session_state.manager.load_routes_from_data(data_tuples)
                        st.session_state.routes_loaded = True
                        
                        st.success(f"Successfully loaded {len(data_tuples)} routes!")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Error loading file: {str(e)}")
            
            # Sample data option
            st.markdown("---")
            st.write("Or use sample data:")
            if st.button("Load Sample Data"):
                sample_data = [
                    ("ITEM1|ITEM2|ITEM3|ITEM4", 0, 3, 0),
                    ("ITEM5|ITEM6|ITEM4|ITEM7|ITEM8", 3, 0, 0),
                    ("ITEM9|ITEM8", 3, 0, 0),
                    ("ITEM10|ITEM8", 245, 6, 0),
                    ("ITEM4|ITEM10", 17, 0, 0),
                    ("ITEM8|ITEM11|ITEM12|ITEM13", 15, 0, 0),
                    ("ITEM4|ITEM7|ITEM8", 18, 30, 3),
                    ("ITEM7|ITEM8", 29, 51, 0),
                    ("ITEM4|ITEM14", 242, 9, 15),
                    ("ITEM4|ITEM8", 255, 0, 0),
                ]

                st.session_state.manager = OpticalNetworkManager()
                st.session_state.manager.load_routes_from_data(sample_data)
                st.session_state.routes_loaded = True
                st.success("Sample data loaded successfully!")
                st.rerun()
        
        with tab2:
            if st.session_state.routes_loaded:
                manager = st.session_state.manager
                
                # Create routes dataframe
                routes_data = []
                for route_id, route in manager.routes.items():
                    bandwidth_used = route.get_total_bandwidth_gbps()
                    capacity = route.get_total_capacity_gbps()
                    utilization = route.get_utilization_percent()
                    
                    # Determine card type
                    card_type = "OCH-400" if capacity > 19200 else "OCH-200"
                    
                    routes_data.append({
                        'Route ID': route_id,
                        'Path': ' → '.join(route.path),
                        'Length': len(route.path),
                        '100G Traffic': next((v for k, v in route.traffic.items() if (hasattr(k, 'value') and k.value == '100G') or k == '100G'), 0),
                        '10G Traffic': next((v for k, v in route.traffic.items() if (hasattr(k, 'value') and k.value == '10G') or k == '10G'), 0),
                        '1G Traffic': next((v for k, v in route.traffic.items() if (hasattr(k, 'value') and k.value == '1G') or k == '1G'), 0),
                        'Bandwidth Used (Gbps)': f"{bandwidth_used:,.0f}",
                        'Capacity (Gbps)': f"{capacity:,.0f}",
                        'Utilization (%)': f"{utilization:.1f}",
                        'Card Type': card_type
                    })
                
                df_routes = pd.DataFrame(routes_data)
                st.dataframe(df_routes, use_container_width=True)
                
                # Route details
                if routes_data:
                    selected_route = st.selectbox("Select route for details:", 
                                                [r['Route ID'] for r in routes_data])
                    
                    if selected_route:
                        route = manager.routes[selected_route]
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Route Information:**")
                            st.write(f"• Path: {' → '.join(route.path)}")
                            st.write(f"• Length: {len(route.path)} nodes")
                            
                            st.write("**Traffic Details:**")
                            total_connections = 0
                            for traffic_type in TrafficType:
                                count = route.traffic.get(traffic_type, 0)
                                if count > 0:
                                    bandwidth = count * traffic_type.capacity_gbps
                                    st.write(f"• {traffic_type.value}: {count} connections ({bandwidth} Gbps)")
                                    total_connections += count
                            
                            if total_connections == 0:
                                st.write("• No traffic on this route")
                        
                        with col2:
                            st.write("**OCH Configuration:**")
                            bandwidth_used = route.get_total_bandwidth_gbps()
                            capacity = route.get_total_capacity_gbps()
                            utilization = route.get_utilization_percent()
                            
                            st.write(f"• Total Bandwidth Used: {bandwidth_used:,.0f} Gbps")
                            st.write(f"• OCH Capacity: {capacity:,.0f} Gbps")
                            st.write(f"• Available: {capacity - bandwidth_used:,.0f} Gbps")
                            
                            # Progress bar with proper capping
                            progress_value = min(utilization, 100) / 100
                            st.progress(progress_value, f"Utilization: {utilization:.1f}%")
                            
                            if utilization > 100:
                                st.error("⚠️ Route overloaded! Needs card upgrade.")
                            elif utilization > 90:
                                st.warning("⚠️ High utilization - consider monitoring")
                            
                            # Card information
                            if route.cards:
                                first_location = list(route.cards.keys())[0]
                                first_card = route.cards[first_location][0]
                                st.write(f"• Card Type: {first_card.card_type.value}")
                                st.write(f"• Number of Card Locations: {len(route.cards)}")
            else:
                st.info("No routes loaded yet.")
        
        with tab3:
            if st.session_state.routes_loaded:
                # Export functionality
                st.write("Export current network state:")
                
                manager = st.session_state.manager
                export_data = []
                
                for route_id, route in manager.routes.items():
                    bandwidth_used = route.get_total_bandwidth_gbps()
                    capacity = route.get_total_capacity_gbps()
                    utilization = route.get_utilization_percent()
                    
                    # Determine card type
                    card_type = "OCH-400" if capacity > 19200 else "OCH-200"
                    
                    # Extract traffic values
                    traffic_100g = next((v for k, v in route.traffic.items() if (hasattr(k, 'value') and k.value == '100G') or k == '100G'), 0)
                    traffic_10g = next((v for k, v in route.traffic.items() if (hasattr(k, 'value') and k.value == '10G') or k == '10G'), 0)
                    traffic_1g = next((v for k, v in route.traffic.items() if (hasattr(k, 'value') and k.value == '1G') or k == '1G'), 0)
                    
                    export_data.append({
                        'Route ID': route_id,
                        'Path': ' → '.join(route.path),
                        'Length': len(route.path),
                        '100G Traffic': traffic_100g,
                        '10G Traffic': traffic_10g,
                        '1G Traffic': traffic_1g,
                        'Bandwidth Used (Gbps)': round(bandwidth_used, 2),
                        'Capacity (Gbps)': round(capacity, 2),
                        'Utilization (%)': round(utilization, 1),
                        'Card Type': card_type
                    })
                
                df_export = pd.DataFrame(export_data)
                
                # Convert to Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_export.to_excel(writer, sheet_name='Routes', index=False)
                
                st.download_button(
                    label="📥 Download Full Network Report (Excel)",
                    data=output.getvalue(),
                    file_name="network_routes_full_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No data to export.")
    
    elif page == "🚀 Simulation":
        simulate_injection_ui()
        
        # Simulation history
        if st.session_state.simulation_history:
            st.subheader("📚 Simulation History")
            
            history_df = pd.DataFrame(st.session_state.simulation_history)
            st.dataframe(history_df, use_container_width=True)
            
            # Statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Simulations", len(history_df))
            with col2:
                st.metric("Total Cost", f"€{history_df['cost'].sum():,.0f}")
            with col3:
                most_used = history_df['option_type'].mode()
                st.metric("Most Used Option", most_used.iloc[0] if len(most_used) > 0 else "N/A")
            
            if st.button("Clear History"):
                st.session_state.simulation_history = []
                st.rerun()
    
    # In your main app, when user selects the Configuration page:
    elif page == "⚙️ Configuration":

        manager = st.session_state.manager
        configuration_panel(manager)

    elif page == "📈 Analytics":
        if not st.session_state.routes_loaded:
            st.info("Please load routes first to view analytics")
        else:
            st.subheader("📈 Advanced Analytics")
            
            manager = st.session_state.manager
            
            # Create analytics charts
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=('Route Utilization Distribution', 'Traffic by Type', 
                              'Card Type Distribution', 'Bandwidth Usage'),
                specs=[[{"type": "histogram"}, {"type": "pie"}],
                       [{"type": "pie"}, {"type": "bar"}]]
            )
            
            # Data preparation
            utilizations = []
            traffic_by_type = {t: 0 for t in TrafficType}
            card_counts = {'OCH-200': 0, 'OCH-400': 0}
            route_bandwidths = []
            route_names = []
            
            for route_id, route in manager.routes.items():
                util = route.get_utilization_percent()
                utilizations.append(util)
                
                for traffic_type in TrafficType:
                    traffic_by_type[traffic_type] += route.traffic.get(traffic_type, 0)
                
                # Card counting
                for cards_list in route.cards.values():
                    for card in cards_list:
                        card_counts[card.card_type.value] += 1
                
                bandwidth = route.get_total_bandwidth_gbps()
                route_bandwidths.append(bandwidth)
                route_names.append(route_id[:20] + "..." if len(route_id) > 20 else route_id)
            
            # Utilization histogram
            if utilizations:
                fig.add_trace(
                    go.Histogram(x=utilizations, nbinsx=10, name="Utilization %"),
                    row=1, col=1
                )
            
            # Traffic pie chart
            traffic_values = [traffic_by_type[t] for t in TrafficType]
            traffic_labels = [f'{t.value} ({v})' for t, v in zip(TrafficType, traffic_values)]
            fig.add_trace(
                go.Pie(labels=traffic_labels, values=traffic_values, name="Traffic"),
                row=1, col=2
            )
            
            # Card distribution
            fig.add_trace(
                go.Pie(labels=list(card_counts.keys()), values=list(card_counts.values()), name="Cards"),
                row=2, col=1
            )
            
            # Top bandwidth routes
            if route_bandwidths:
                top_routes_idx = np.argsort(route_bandwidths)[-10:]  # Top 10
                top_bandwidths = [route_bandwidths[i] for i in top_routes_idx]
                top_names = [route_names[i] for i in top_routes_idx]
                
                fig.add_trace(
                    go.Bar(x=top_names, y=top_bandwidths, name="Bandwidth (Gbps)"),
                    row=2, col=2
                )
            
            fig.update_layout(height=800, showlegend=True, title_text="Network Analytics Dashboard")
            st.plotly_chart(fig, use_container_width=True)
            
            # Network metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                avg_util = np.mean(utilizations) if utilizations else 0
                st.metric("Average Utilization", f"{avg_util:.1f}%")
            
            with col2:
                max_util = max(utilizations) if utilizations else 0
                st.metric("Max Utilization", f"{max_util:.1f}%")
            
            with col3:
                overloaded = sum(1 for u in utilizations if u > 100)
                st.metric("Overloaded Routes", overloaded)
            
            with col4:
                total_bandwidth = sum(route_bandwidths)
                st.metric("Total Bandwidth", f"{total_bandwidth:,.0f} Gbps")

if __name__ == "__main__":
    # Check if running properly with streamlit
    import sys
    if 'streamlit' not in sys.modules:
        print("please install Streamlit !")
    else:
        main()