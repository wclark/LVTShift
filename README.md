# LVTShift

**LVTShift** is a toolkit for modeling Land Value Tax (LVT) shifts in counties across the United States. It provides utilities for fetching, processing, and analyzing parcel, tax, and census data, and includes examp![clelogo](https://github.com/user-attachments/assets/56c1e371-2677-49b0-bc7f-bdb5c663ebb3)
le workflows for real-world counties.

## Features

- Fetch and join Census demographic and boundary data (`census_utils.py`)
- Model property tax and LVT scenarios (`lvt_utils.py`)
- Example: South Bend, IN analysis notebook (`examples/southbend.ipynb`)

## Getting Started

1. Clone the repo:
   ```sh
   git clone https://github.com/YOURUSERNAME/LVTShift.git
   cd LVTShift
   ```

2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

3. Explore the example notebook:
   ```sh
   cd examples
   jupyter notebook southbend.ipynb
   ```

## File Structure
