# Optical Network Transmission Manager

A comprehensive web-based tool for managing and optimizing optical network infrastructure, built with Streamlit.

## Overview

This application helps network engineers and planners manage optical transport networks by:
- Visualizing network topology and route configurations
- Simulating traffic injection scenarios
- Optimizing OCH (Optical Channel) card allocation
- Analyzing network utilization and capacity
- Supporting multiple traffic types (100G, 10G, 1G)

## Features

### Dashboard
- Interactive network topology visualization
- Real-time network statistics and utilization metrics
- Card distribution and traffic summaries

### Data Management
- Import network routes from Excel files
- View and analyze existing route configurations
- Export network state for reporting

### Traffic Simulation
- Combined traffic injection planning (100G, 10G, 1G)
- Multiple injection options with cost analysis
- Automatic route optimization (existing, new, or modified routes)
- Simulation history tracking

### Configuration
- Customizable OCH card specifications (OCH-200, OCH-400)
- Adjustable cost parameters for network modifications
- Traffic efficiency settings for bandwidth calculations
- Persistent configuration across sessions

### Analytics
- Route utilization distribution
- Traffic breakdown by type
- Card type distribution
- Bandwidth usage analysis
- Top bandwidth consumers identification

## Installation

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/freefunction/Network_Manger.git
cd Network_Manger
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## Usage

### Loading Data

1. Navigate to **Data Management** > **Upload Data**
2. Upload an Excel file with columns: `Route`, `100G`, `10G`, `1G`
3. Or use the sample data for testing

### Configuring the Network

1. Go to **Configuration**
2. Set OCH card specifications (channels, capacity)
3. Configure costs (card costs, converter costs)
4. Adjust traffic efficiency multipliers
5. Click **Apply Configuration**

### Simulating Traffic Injection

1. Navigate to **Simulation**
2. Select source and destination nodes
3. Specify traffic amounts (100G, 10G, 1G)
4. Click **Find Injection Options**
5. Review options sorted by cost
6. Apply the preferred option

### Analyzing the Network

1. Go to **Analytics** to view:
   - Utilization distributions
   - Traffic type breakdown
   - Card allocation statistics
   - Bandwidth usage trends

## Data Format

Input Excel files should have the following structure:

| Route | 100G | 10G | 1G |
|-------|------|-----|-----|
| NodeA\|NodeB\|NodeC | 5 | 10 | 2 |
| NodeD\|NodeE | 3 | 0 | 5 |

- **Route**: Pipe-separated list of nodes (e.g., `BRDT|TITN|NOSS`)
- **100G/10G/1G**: Number of connections for each traffic type

## Technical Details

### OCH Card Types

- **OCH-200**: Default 96 channels × 200 Gbps = 19,200 Gbps total
- **OCH-400**: Default 64 channels × 400 Gbps = 25,600 Gbps total

### Traffic Types

- **100G**: 100 Gbps per connection
- **10G**: 10 Gbps per connection
- **1G**: 1 Gbps per connection

### Injection Options

1. **EXISTING**: Use available capacity on existing routes (€0 cost)
2. **NEW**: Create new direct route with new OCH cards
3. **MODIFY**: Inject into existing route with converters and additional cards

## Dependencies

- Python 3.8+
- Streamlit 1.28+
- Pandas 2.0+
- Plotly 5.17+
- NetworkX 3.1+
- NumPy 1.24+

See `requirements.txt` for complete list.

## Configuration Persistence

The application uses Streamlit's session state to maintain:
- OCH card configurations
- Cost parameters
- Traffic efficiency settings
- Network routes and topology
- Simulation history

Configuration persists within a user session but resets on page refresh.

## Deployment

### Streamlit Community Cloud

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repository
4. Deploy with one click

### Other Platforms

The app can be deployed on:
- Heroku
- AWS/GCP/Azure
- Docker containers
- Any platform supporting Python web apps

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License - feel free to use and modify as needed.

## Support

For questions or issues, please open an issue on GitHub or contact the maintainer.

## Acknowledgments

Built for optical network planning and optimization in telecommunications infrastructure management.
