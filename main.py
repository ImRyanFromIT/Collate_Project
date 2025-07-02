import openai
import json
import sys
import os
import gspread
from google.oauth2.service_account import Credentials
import glob

def parse_ticket(ticket_text):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": """Extract ALL hostnames and their specific issue types from the ticket. 
            Required format:
                {
                    "hosts": [
                        {
                            "hostname": "string",
                            "confidence": "high|medium|low",
                            "context": "why this was identified"
                            "context explanation": "why confidence is high|medium|low"
                        }
                    ],
                    "issue_type": "reboot|maintenance",
                    "ambiguities": ["list any unclear aspects"]
                }
            
            Hostname examples:
            - web01.company.com
            - db-prod-01
            - app-server-03.internal
            - mail.example.org
            - hostname starts with 'x' and is 8 characters long
            - xoabbypr 
            
            Look for server names, computer names, domain names, or any identifier that represents a specific machine/server.
            
            Issue types:
            - "reboot" for restart, reboot, not restarted, unresponsive, hung, frozen
            - "maintenance" for failed updates, patches, maintenance issues, updates
            - If you are not confident, mark as "unsure"
            
            Each hostname should be paired with its specific issue based on the context in the ticket."""},
            {"role": "user", "content": ticket_text}
        ],
        temperature=0.1
    )
    
    content = response.choices[0].message.content
    if content is None:
        return {"error": "No content received from API"}
    return json.loads(content)

def get_support_group(hostname):
    """
    Query Google Sheet to find support group for a given hostname. Explicit search
    
    Args:
        hostname (str): The hostname to look up
        
    Returns:
        dict: {
            "hostname": str,
            "support_group": str or None,
            "found": bool
        }
    """
    try:
        # Handles google sheet direction and auth. Needs local json file from gcp
        scope = ['https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive']
        
        creds = Credentials.from_service_account_file('linux-project-464606-a2b6ecdaa8b5.json', scopes=scope)
        client = gspread.authorize(creds)
        
        sheet_id = '1A-3r8ybBk45hyFnGRpzItY4rtRMfrjCx9PKVFeysMGc'
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet('Sheet1')
        
        # Gets ALL values in sheet, needs to be cleaned up
        all_values = worksheet.get_all_values()
        
        # Skip headers, select columns 'A' and 'C', needs to be cleaned up
        for row in all_values[1:]:  # SKIP HEADER!!
            if len(row) > 2 and row[2].strip().upper() == hostname.strip().upper():
                support_group = row[0] if len(row) > 0 else None  # Column A (index 0)
                return {
                    "hostname": hostname,
                    "support_group": support_group,
                    "found": True
                }
        
        # Hostname not found
        return {
            "hostname": hostname,
            "support_group": None,
            "found": False
        }
        
    except Exception as e:
        return {
            "hostname": hostname,
            "support_group": None,
            "found": False,
            "error": str(e)
        }

def get_app_owners(support_group):
    """
    Query second Google Sheet to find app owners and contacts for a given support group.
    
    Args:
        support_group (str): The support group name to look up
        
    Returns:
        dict: {
            "support_group": str,
            "app_owners": str or None,
            "email_distros": str or None,
            "individual_contacts": str or None,
            "found": bool
        }
    """
    try:
        # Set up credentials and authorize
        scope = ['https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive']
        
        creds = Credentials.from_service_account_file('linux-project-464606-a2b6ecdaa8b5.json', scopes=scope)
        client = gspread.authorize(creds)
        
        # Open the second Google Sheet
        sheet_id = '1X5Cj4xlL0iW4S9QgH4v58TRSiP9voBDZxBMiboWPmEk'
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet('Sheet1')
        
        # Get all values from the sheet
        all_values = worksheet.get_all_values()
        
        # Skip header row and search for support group in Column A (index 0)
        for row in all_values[1:]:  # Skip header
            if len(row) > 0 and row[0].strip().upper() == support_group.strip().upper():
                app_owners = row[0] if len(row) > 0 else None  # Column A (index 0)
                email_distros = row[1] if len(row) > 1 else None  # Column B (index 1)
                individual_contacts = row[2] if len(row) > 2 else None  # Column C (index 2)
                
                return {
                    "support_group": support_group,
                    "app_owners": app_owners,
                    "email_distros": email_distros,
                    "individual_contacts": individual_contacts,
                    "found": True
                }
        
        # Support group not found in app owners sheet
        return {
            "support_group": support_group,
            "app_owners": None,
            "email_distros": None,
            "individual_contacts": None,
            "found": False,
            "message": f"Support group '{support_group}' not found in app owners sheet"
        }
        
    except Exception as e:
        return {
            "support_group": support_group,
            "app_owners": None,
            "email_distros": None,
            "individual_contacts": None,
            "found": False,
            "error": str(e)
        }

def collate_ticket_results(ticket_content):
    """
    Process a ticket and collate results grouped by support group.
    
    Args:
        ticket_content (str): The raw ticket text
        
    Returns:
        dict: {
            "summary": {
                "total_hostnames": int,
                "total_support_groups": int,
                "successful_lookups": int,
                "failed_lookups": int
            },
            "groups": {
                "Support Group Name": {
                    "support_group": str,
                    "hostnames": [str],
                    "email_distros": str,
                    "individual_contacts": str,
                    "issue_types": [str],
                    "hostname_details": {...}
                }
            },
            "errors": {
                "hostnames_not_found": [str],
                "support_groups_not_found": [str],
                "other_errors": [str]
            }
        }
    """
    # Step 1: Parse the ticket to get hostnames
    parsed_result = parse_ticket(ticket_content)
    
    if 'error' in parsed_result:
        return {
            "summary": {"total_hostnames": 0, "total_support_groups": 0, "successful_lookups": 0, "failed_lookups": 0},
            "groups": {},
            "errors": {"hostnames_not_found": [], "support_groups_not_found": [], "other_errors": [f"Ticket parsing failed: {parsed_result['error']}"]}
        }
    
    if 'hosts' not in parsed_result or not parsed_result['hosts']:
        return {
            "summary": {"total_hostnames": 0, "total_support_groups": 0, "successful_lookups": 0, "failed_lookups": 0},
            "groups": {},
            "errors": {"hostnames_not_found": [], "support_groups_not_found": [], "other_errors": ["No hostnames found in ticket"]}
        }
    
    # Initialize tracking variables
    groups = {}
    errors = {"hostnames_not_found": [], "support_groups_not_found": [], "other_errors": []}
    issue_type = parsed_result.get('issue_type', 'unknown')
    
    # Step 2: Process each hostname
    for host in parsed_result['hosts']:
        hostname = host.get('hostname', '') if isinstance(host, dict) else str(host)
        if not hostname:
            continue
            
        # Get support group for hostname
        support_info = get_support_group(hostname)
        
        if not support_info.get('found'):
            errors["hostnames_not_found"].append(hostname)
            if 'error' in support_info:
                errors["other_errors"].append(f"Error looking up {hostname}: {support_info['error']}")
            continue
        
        support_group = support_info['support_group']
        
        # Get app owners for support group
        app_owner_info = get_app_owners(support_group)
        
        if not app_owner_info.get('found'):
            errors["support_groups_not_found"].append(support_group)
            if 'error' in app_owner_info:
                errors["other_errors"].append(f"Error looking up app owners for {support_group}: {app_owner_info['error']}")
        
        # Group by support group
        if support_group not in groups:
            groups[support_group] = {
                "support_group": support_group,
                "hostnames": [],
                "email_distros": app_owner_info.get('email_distros'),
                "individual_contacts": app_owner_info.get('individual_contacts'),
                "issue_types": [],
                "hostname_details": {}
            }
        
        # Add hostname to group
        groups[support_group]["hostnames"].append(hostname)
        
        # Add issue type if not already present
        if issue_type not in groups[support_group]["issue_types"]:
            groups[support_group]["issue_types"].append(issue_type)
        
        # Store detailed hostname info
        groups[support_group]["hostname_details"][hostname] = {
            "hostname": hostname,
            "confidence": host.get('confidence', 'unknown') if isinstance(host, dict) else 'unknown',
            "context": host.get('context', '') if isinstance(host, dict) else '',
            "support_group_found": support_info.get('found', False),
            "app_owners_found": app_owner_info.get('found', False)
        }
    
    # Step 3: Generate summary
    total_hostnames = len(parsed_result['hosts'])
    successful_lookups = sum(len(group["hostnames"]) for group in groups.values())
    failed_lookups = len(errors["hostnames_not_found"])
    
    summary = {
        "total_hostnames": total_hostnames,
        "total_support_groups": len(groups),
        "successful_lookups": successful_lookups,
        "failed_lookups": failed_lookups,
        "coverage_percentage": int(round((successful_lookups / total_hostnames * 100) if total_hostnames > 0 else 0))
    }
    
    return {
        "summary": summary,
        "groups": groups,
        "errors": errors
    }

# command switches for debugging purposes
if len(sys.argv) > 2 and sys.argv[1] == "--ticket":
    with open(sys.argv[2], 'r') as f:
        ticket_content = f.read()
    
    print(f"Ticket: {ticket_content.strip()}\n")
    result = parse_ticket(ticket_content)
    print(json.dumps(result, indent=2))
elif len(sys.argv) > 2 and sys.argv[1] == "--lookup":
    hostname = sys.argv[2]
    print(f"Looking up hostname: {hostname}\n")
    result = get_support_group(hostname)
    print(json.dumps(result, indent=2))
elif len(sys.argv) > 2 and sys.argv[1] == "--app-owners":
    support_group = sys.argv[2]
    print(f"Looking up app owners for support group: {support_group}\n")
    result = get_app_owners(support_group)
    print(json.dumps(result, indent=2))
elif len(sys.argv) > 2 and sys.argv[1] == "--combined":
    with open(sys.argv[2], 'r') as f:
        ticket_content = f.read()
    
    print(f"Ticket: {ticket_content.strip()}\n")
    
    # Parse the ticket first
    parsed_result = parse_ticket(ticket_content)
    print("Parsed ticket:")
    print(json.dumps(parsed_result, indent=2))
    
    # Look up support groups and app owners for each hostname found
    if 'hosts' in parsed_result:
        print("\nComplete lookup chain:")
        for host in parsed_result['hosts']:
            hostname = host.get('hostname', '') if isinstance(host, dict) else str(host)
            if hostname:
                print(f"\n--- {hostname} ---")
                
                # Step 1: Get support group
                support_info = get_support_group(hostname)
                print(f"Support Group: {json.dumps(support_info, indent=2)}")
                
                # Step 2: Get app owners (if support group was found)
                if support_info.get('found') and support_info.get('support_group'):
                    app_owner_info = get_app_owners(support_info['support_group'])
                    print(f"App Owners: {json.dumps(app_owner_info, indent=2)}")
                else:
                    print("App Owners: Skipped (support group not found)")
elif len(sys.argv) > 2 and sys.argv[1] == "--full-lookup":
    hostname = sys.argv[2]
    print(f"Full lookup chain for hostname: {hostname}\n")
    
    # Step 1: Get support group
    support_info = get_support_group(hostname)
    print("Step 1 - Support Group:")
    print(json.dumps(support_info, indent=2))
    
    # Step 2: Get app owners (if support group was found)
    if support_info.get('found') and support_info.get('support_group'):
        print(f"\nStep 2 - App Owners:")
        app_owner_info = get_app_owners(support_info['support_group'])
        print(json.dumps(app_owner_info, indent=2))
    else:
        print(f"\nStep 2 - App Owners: Skipped (support group not found)")
elif len(sys.argv) > 2 and sys.argv[1] == "--collate":
    with open(sys.argv[2], 'r') as f:
        ticket_content = f.read()
    
    print(f"Collating ticket: {sys.argv[2]}\n")
    print(f"Content: {ticket_content.strip()}\n")
    
    result = collate_ticket_results(ticket_content)
    print("Collated Results:")
    print(json.dumps(result, indent=2))
elif len(sys.argv) > 2 and sys.argv[1] == "--batch":
    # Batch processing with collation - can handle multiple files or directories
    ticket_files = []
    
    for arg in sys.argv[2:]:
        if os.path.isdir(arg):
            # If it's a directory, get all .txt files in it
            pattern = os.path.join(arg, "*.txt")
            ticket_files.extend(glob.glob(pattern))
        elif os.path.isfile(arg):
            # If it's a file, add it directly
            ticket_files.append(arg)
        elif "*" in arg or "?" in arg:
            # If it's a glob pattern, expand it
            ticket_files.extend(glob.glob(arg))
        else:
            print(f"Warning: '{arg}' not found or not a valid file/directory/pattern")
    
    if not ticket_files:
        print("No ticket files found to process!")
    else:
        print(f"Processing {len(ticket_files)} ticket files with collation...\n")
        
        # Aggregate data across all tickets
        all_groups = {}
        all_errors = {"hostnames_not_found": [], "support_groups_not_found": [], "other_errors": []}
        total_summary = {"total_hostnames": 0, "total_support_groups": 0, "successful_lookups": 0, "failed_lookups": 0}
        
        for i, ticket_file in enumerate(ticket_files, 1):
            print(f"{'='*60}")
            print(f"TICKET {i}/{len(ticket_files)}: {ticket_file}")
            print(f"{'='*60}")
            
            try:
                with open(ticket_file, 'r') as f:
                    ticket_content = f.read()
                
                print(f"Content: {ticket_content.strip()}\n")
                
                # Collate this ticket
                ticket_result = collate_ticket_results(ticket_content)
                
                # Display individual ticket summary
                print("Ticket Summary:")
                print(json.dumps(ticket_result["summary"], indent=2))
                
                if ticket_result["errors"]["other_errors"]:
                    print(f"Errors: {ticket_result['errors']['other_errors']}")
                
                # Aggregate into overall results
                total_summary["total_hostnames"] += ticket_result["summary"]["total_hostnames"]
                total_summary["successful_lookups"] += ticket_result["summary"]["successful_lookups"]
                total_summary["failed_lookups"] += ticket_result["summary"]["failed_lookups"]
                
                # Merge groups (hostnames from multiple tickets can be in same group)
                for group_name, group_data in ticket_result["groups"].items():
                    if group_name not in all_groups:
                        all_groups[group_name] = group_data.copy()
                    else:
                        # Merge hostnames and issue types
                        all_groups[group_name]["hostnames"].extend(group_data["hostnames"])
                        all_groups[group_name]["hostname_details"].update(group_data["hostname_details"])
                        for issue_type in group_data["issue_types"]:
                            if issue_type not in all_groups[group_name]["issue_types"]:
                                all_groups[group_name]["issue_types"].append(issue_type)
                
                # Merge errors
                all_errors["hostnames_not_found"].extend(ticket_result["errors"]["hostnames_not_found"])
                all_errors["support_groups_not_found"].extend(ticket_result["errors"]["support_groups_not_found"])
                all_errors["other_errors"].extend(ticket_result["errors"]["other_errors"])
                
                print("\n")
                
            except Exception as e:
                print(f"Error processing {ticket_file}: {str(e)}\n")
                all_errors["other_errors"].append(f"Failed to process {ticket_file}: {str(e)}")
        
        # Calculate final summary
        total_summary["total_support_groups"] = len(all_groups)
        total_summary["coverage_percentage"] = int(round((total_summary["successful_lookups"] / total_summary["total_hostnames"] * 100) if total_summary["total_hostnames"] > 0 else 0))
        
        # Display final aggregated results
        print("="*80)
        print("FINAL AGGREGATED RESULTS")
        print("="*80)
        
        final_result = {
            "summary": total_summary,
            "groups": all_groups,
            "errors": all_errors
        }
        
        print(json.dumps(final_result, indent=2))
else:
    print("Usage:")
    print("  python main.py --ticket <filename>        # Parse a ticket file")
    print("  python main.py --lookup <hostname>        # Look up support group for hostname")
    print("  python main.py --app-owners <group>       # Look up app owners for support group")
    print("  python main.py --full-lookup <hostname>   # Complete hostname → support group → app owners")
    print("  python main.py --combined <filename>      # Parse ticket and complete lookup chain")
    print("  python main.py --collate <filename>       # Parse ticket and group hostnames by support group")
    print("  python main.py --batch <files/dirs>       # Batch process and collate multiple ticket files")
    print("")
    print("Batch examples:")
    print("  python main.py --batch ticket1.txt ticket2.txt    # Process specific files")
    print("  python main.py --batch tickets/                   # Process all .txt files in directory")
    print("  python main.py --batch 'ticket*.txt'             # Process files matching pattern")