# ChakraOps

A Python application for managing operations.

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/swap2you/chakraops.git
   cd chakraops
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```

3. Activate the virtual environment:
   - Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - Linux/Mac:
     ```bash
     source .venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Configure the application (optional):
   - Copy `.env.example` to `.env` and fill in your values
   - Copy `config.yaml.example` to `config.yaml` and customize as needed

## Run

```bash
python main.py
```

The application should print "ChakraOps boot OK" and exit successfully.

## Development

- Application code is in the `app/` directory
- Tests are in the `tests/` directory
- Scripts are in the `scripts/` directory
