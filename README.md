# Ticket Processing System

A streamlined system that automatically extracts hostnames from IT tickets and routes them to the appropriate support teams.

##  What It Does

1. **Extracts hostnames** from ticket text using OpenAI
2. **Looks up support groups** for each hostname via Google Sheets
3. **Finds contact information** for support teams
4. **Groups results** by support team for efficient notification

##  Quick Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure the system:**
   - Update `config.json` with your OpenAI API key
   - Place your Google Service Account credentials in the project folder
   - Update Google Sheets IDs in config if using different sheets

3. **Ready to go!**

##  Basic Usage

### Simple hostname extraction:
```python
from main_simplified import parse_ticket

ticket_text = "Server CLOUD-LNX-DOCK01 is not responding"
result = parse_ticket(ticket_text)
print(result['hostnames'])  # ['CLOUD-LNX-DOCK01']
```

### Complete ticket processing:
```python
from main_simplified import process_ticket

results = process_ticket("Issues with CLOUD-LNX-DOCK01 and DATAN-LNX-HADOOP01")
# Returns grouped results by support team with contact info
```

### Individual lookups:
```python
from main_simplified import get_support_group, get_app_owners

# Find support group for a hostname
support = get_support_group("CLOUD-LNX-DOCK01")

# Get contacts for a support group
contacts = get_app_owners("Linux Cloud Team")
```

##  Key Features

- **Smart Parsing**: Uses AI to reliably extract hostnames from natural language
- **Efficient Caching**: 1-hour cache reduces API calls and improves performance  
- **Batch Processing**: Handle multiple hostnames in a single operation
- **Flexible Integration**: Use individual functions or complete workflow
- **Error Handling**: Graceful handling of missing hostnames/support groups

##  Project Structure

```
├── main_simplified.py      # Core processing functions
├── example_usage.py        # Usage examples and patterns
├── config.json            # Configuration settings
├── requirements.txt       # Python dependencies
└── *.json                 # Google Service Account credentials
```

##  Configuration

Edit `config.json` to customize:
- **OpenAI settings**: API key, model, temperature
- **Google Sheets**: Sheet IDs and credentials file
- **Caching**: Enable/disable and TTL settings

##  Learn More

Run `python example_usage.py` to see detailed examples of all functionality.

---
