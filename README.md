# LinuxProject
Multi-step ticket processing system for automated hostname identification and support group routing.

## Overview
This system processes IT support tickets to automatically identify hostnames, determine responsible support groups, and gather contact information for efficient incident routing. Sheets in repo are copies of sheets being called via API. 

## Workflow
```
1. Ticket Input → 2. Parse Hostnames → 3. Lookup Support Groups → 4. Lookup App Owners → 5. Collate by Group → 6. Ready for Email
```

### Detailed Process:
1. **Ticket Parsing**: Uses GPT3.5 to extract hostnames and issue types from unstructured ticket text
2. **Support Group Lookup**: API call to Support Group SoT sheet to find support group for a hostname
3. **App Owner Lookup**: API call to App Owners Data sheet to find contact information for a support group
4. **Collation**: Groups all results by support group for efficient communication
5. **Output**: Structured data ready for email generation or manual review

## Core Functions

### `parse_ticket(ticket_text)`
- **Purpose**: Extract hostnames and issue types from ticket text using OpenAI
- **Input**: Raw ticket content (string)
- **Output**: Structured data with hostnames, confidence levels, and issue types
- **AI Model**: GPT-3.5-turbo

### `get_support_group(hostname)`
- **Purpose**: API call to Support Group SoT sheet to find support group for a hostname
- **Input**: Hostname (string)
- **Output**: Support group name and lookup status
- **Data Source**: Google Sheets (Column A: Support Group, Column C: Server Name)

### `get_app_owners(support_group)`
- **Purpose**: API call to App Owners Data sheet to find contact information for a support group
- **Input**: Support group name (string)
- **Output**: App owners, email distros, and individual contacts
- **Data Source**: Google Sheets (Column A: App Owner, Column B: Email Distros, Column C: Individual Contacts)

### `collate_ticket_results(ticket_content)`
- **Purpose**: Complete end-to-end processing with grouping by support group!
- **Input**: Raw ticket content (string)
- **Output**: Hostnames grouped by support group with summary statistics
- **Benefits**: Reduces duplicate communications, organizes results for email routing

## Command Line Interface

### Individual Functions
```bash
# Parse a single ticket file
python main.py --ticket <filename>

# Look up support group for a specific hostname
python main.py --lookup <hostname>

# Look up app owners for a specific support group
python main.py --app-owners <support_group>

# Complete lookup chain for single hostname
python main.py --full-lookup <hostname>

# Parse ticket and perform complete lookup chain
python main.py --combined <filename>

# Parse ticket and group results by support group
python main.py --collate <filename>
```

### Batch Processing
```bash
# Process multiple ticket files with collation
python main.py --batch <files/directories>

# Examples:
python main.py --batch ticket1.txt ticket2.txt ticket3.txt
python main.py --batch tickets/
python main.py --batch "ticket*.txt"
```

## Configuration Requirements

### Google Sheets Setup
1. **Sheet 1**: Support Group mapping
   - Column A: Support Group
   - Column C: Server Name/Hostname
   
2. **Sheet 2**: App Owner contacts
   - Column A: Remedy application name (app owner)
   - Column B: Email distros
   - Column C: Individual contacts

### API Keys
- **OpenAI API Key**: Set as environment variable `OPENAI_API_KEY`
- **Google Service Account**: JSON file (`linux-project-464606-a2b6ecdaa8b5.json`)

### Dependencies
```bash
pip install -r requirements.txt
```

## Sample Output Structure

### Collated Results
```json
{
  "summary": {
    "total_hostnames": 4,
    "total_support_groups": 2,
    "successful_lookups": 3,
    "failed_lookups": 1,
    "coverage_percentage": 75
  },
  "groups": {
    "Linux Support Team": {
      "support_group": "Linux Support Team",
      "hostnames": ["QATEST-LNX-AUTO01", "CLOUD-LNX-DOCK01"],
      "email_distros": "linux-support@company.com",
      "individual_contacts": "john.doe@company.com",
      "issue_types": ["reboot", "maintenance"]
    }
  },
  "errors": {
    "hostnames_not_found": ["UNKNOWN-SERVER"],
    "support_groups_not_found": [],
    "other_errors": []
  }
}
```

## Use Cases

### Primary: Batch Ticket Processing
- Process multiple tickets simultaneously
- Group hostnames by support team
- Generate organized contact lists for incident response

### Secondary: Individual Lookups
- Quick hostname-to-support-group lookups
- Verification of contact information
- Testing and debugging data sources

## Error Handling
- **Hostname not found**: Tracked in errors section, processing continues
- **Support group not found**: Tracked separately, partial results preserved
- **API failures**: Graceful degradation with error reporting
- **File not found**: Clear error messages with usage instructions

## Future Enhancements
- Email generation and sending functionality
- API Integration with ticketing systems
- Historical data tracking and analytics (memory)
- Support for fallback to additional data sources
