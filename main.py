#!/usr/bin/env python3
"""
Simplified Ticket Processing System
Focuses on: Hostname extraction and App Owner lookup
"""

import openai
import json
import sys
import os
import gspread
from google.oauth2.service_account import Credentials
from functools import lru_cache
from datetime import datetime, timedelta
import argparse
import glob

# Load configuration
def load_config():
    """Load configuration from config.json"""
    with open('config.json', 'r') as f:
        return json.load(f)

CONFIG = load_config()

# Simple cache implementation
class SimpleCache:
    def __init__(self, ttl_seconds=3600):
        self._cache = {}
        self._ttl = timedelta(seconds=ttl_seconds)
    
    def get(self, key):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key, value):
        self._cache[key] = (value, datetime.now())
    
    def clear(self):
        self._cache.clear()

# Initialize cache
cache = SimpleCache(ttl_seconds=CONFIG['cache']['ttl_seconds'])

def parse_ticket(ticket_text):
    """
    Extract hostnames from ticket text using OpenAI.
    Returns a simple list of hostnames found.
    """
    client = openai.OpenAI(api_key=CONFIG['openai']['api_key'])
    
    response = client.chat.completions.create(
        model=CONFIG['openai']['model'],
        messages=[
            {"role": "system", "content": """Extract ALL hostnames from the ticket text.
            Return a simple JSON list of hostnames found.
            
            Hostname patterns to look for:
            - Server names (e.g., WEB01, DB-PROD-01, APP-SERVER-03)
            - Fully qualified domain names (e.g., server.company.com)
            - Any identifier that represents a specific machine/server
            
            Return format: {"hostnames": ["hostname1", "hostname2", ...]}
            
            If no hostnames found, return: {"hostnames": []}"""},
            {"role": "user", "content": ticket_text}
        ],
        temperature=CONFIG['openai']['temperature']
    )
    
    content = response.choices[0].message.content
    if content is None:
        return {"hostnames": [], "error": "No content received from API"}
    
    try:
        result = json.loads(content)
        return {"hostnames": result.get("hostnames", [])}
    except json.JSONDecodeError:
        return {"hostnames": [], "error": "Failed to parse AI response"}

@lru_cache(maxsize=1)
def get_google_sheets_client():
    """Get authenticated Google Sheets client (cached)"""
    scope = ['https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive']
    
    creds = Credentials.from_service_account_file(
        CONFIG['google_sheets']['credentials_file'], 
        scopes=scope
    )
    return gspread.authorize(creds)

def get_support_group(hostname, use_cache=True):
    """
    Find support group for a hostname.
    Returns: {"hostname": str, "support_group": str|None, "found": bool}
    """
    # Check cache first
    if use_cache and CONFIG['cache']['enabled']:
        cached_result = cache.get(f"support_group:{hostname}")
        if cached_result is not None:
            return cached_result
    
    try:
        client = get_google_sheets_client()
        sheet = client.open_by_key(CONFIG['google_sheets']['support_group_sheet_id'])
        worksheet = sheet.worksheet('Sheet1')
        
        # Get all values (consider using batch_get for better performance)
        all_values = worksheet.get_all_values()
        
        # Search for hostname (Column C, index 2)
        for row in all_values[1:]:  # Skip header
            if len(row) > 2 and row[2].strip().upper() == hostname.strip().upper():
                result = {
                    "hostname": hostname,
                    "support_group": row[0] if len(row) > 0 else None,
                    "found": True
                }
                
                # Cache the result
                if CONFIG['cache']['enabled']:
                    cache.set(f"support_group:{hostname}", result)
                
                return result
        
        # Not found
        result = {"hostname": hostname, "support_group": None, "found": False}
        if CONFIG['cache']['enabled']:
            cache.set(f"support_group:{hostname}", result)
        return result
        
    except Exception as e:
        return {"hostname": hostname, "support_group": None, "found": False, "error": str(e)}

def get_app_owners(support_group, use_cache=True):
    """
    Find app owners for a support group.
    Returns: {"support_group": str, "contacts": {...}, "found": bool}
    """
    # Check cache first
    if use_cache and CONFIG['cache']['enabled']:
        cached_result = cache.get(f"app_owners:{support_group}")
        if cached_result is not None:
            return cached_result
    
    try:
        client = get_google_sheets_client()
        sheet = client.open_by_key(CONFIG['google_sheets']['app_owners_sheet_id'])
        worksheet = sheet.worksheet('Sheet1')
        
        all_values = worksheet.get_all_values()
        
        # Search for support group (Column A, index 0)
        for row in all_values[1:]:  # Skip header
            if len(row) > 0 and row[0].strip().upper() == support_group.strip().upper():
                result = {
                    "support_group": support_group,
                    "contacts": {
                        "app_owner": row[0] if len(row) > 0 else None,
                        "email_distros": row[1] if len(row) > 1 else None,
                        "individual_contacts": row[2] if len(row) > 2 else None
                    },
                    "found": True
                }
                
                # Cache the result
                if CONFIG['cache']['enabled']:
                    cache.set(f"app_owners:{support_group}", result)
                
                return result
        
        # Not found
        result = {"support_group": support_group, "contacts": {}, "found": False}
        if CONFIG['cache']['enabled']:
            cache.set(f"app_owners:{support_group}", result)
        return result
        
    except Exception as e:
        return {"support_group": support_group, "contacts": {}, "found": False, "error": str(e)}

def process_ticket(ticket_content):
    """
    Main processing function: parse ticket and collate results by support group.
    """
    # Step 1: Parse ticket
    parse_result = parse_ticket(ticket_content)
    
    if 'error' in parse_result:
        return {
            "status": "error",
            "message": f"Failed to parse ticket: {parse_result['error']}",
            "results": {}
        }
    
    hostnames = parse_result.get('hostnames', [])
    
    if not hostnames:
        return {
            "status": "success",
            "message": "No hostnames found in ticket",
            "results": {}
        }
    
    # Step 2: Process hostnames and group by support group
    groups = {}
    not_found = []
    
    for hostname in hostnames:
        # Get support group
        support_info = get_support_group(hostname)
        
        if not support_info['found']:
            not_found.append(hostname)
            continue
        
        support_group = support_info['support_group']
        
        # Get app owners
        owner_info = get_app_owners(support_group)
        
        # Group results
        if support_group not in groups:
            groups[support_group] = {
                "hostnames": [],
                "contacts": owner_info.get('contacts', {}) if owner_info['found'] else {},
                "contact_lookup_successful": owner_info['found']
            }
        
        groups[support_group]["hostnames"].append(hostname)
    
    # Step 3: Create summary
    return {
        "status": "success",
        "summary": {
            "total_hostnames": len(hostnames),
            "grouped_into": len(groups),
            "not_found": len(not_found)
        },
        "results": groups,
        "errors": {
            "hostnames_not_found": not_found
        }
    }

def format_results(results):
    """Format results for display"""
    output = []
    
    output.append("\n=== TICKET PROCESSING RESULTS ===\n")
    
    # Summary
    if 'summary' in results:
        output.append(f"Total Hostnames: {results['summary']['total_hostnames']}")
        output.append(f"Support Groups: {results['summary']['grouped_into']}")
        output.append(f"Not Found: {results['summary']['not_found']}\n")
    
    # Group details
    if results.get('results'):
        for group_name, group_data in results['results'].items():
            output.append(f"\n[{group_name}]")
            output.append(f"Hostnames: {', '.join(group_data['hostnames'])}")
            
            contacts = group_data.get('contacts', {})
            if contacts:
                if contacts.get('email_distros'):
                    output.append(f"Email: {contacts['email_distros']}")
                if contacts.get('individual_contacts'):
                    output.append(f"Contacts: {contacts['individual_contacts']}")
            else:
                output.append("Contact information not found")
    
    # Errors
    if results.get('errors', {}).get('hostnames_not_found'):
        output.append(f"\nHostnames not found: {', '.join(results['errors']['hostnames_not_found'])}")
    
    return '\n'.join(output)

def main():
    parser = argparse.ArgumentParser(description='Simplified Ticket Processing System')
    
    # Single ticket processing
    parser.add_argument('--ticket', type=str, help='Process a single ticket file')
    
    # Batch processing
    parser.add_argument('--batch', nargs='+', help='Process multiple ticket files')
    
    # Lookup functions
    parser.add_argument('--lookup', type=str, help='Look up support group for a hostname')
    parser.add_argument('--contacts', type=str, help='Look up contacts for a support group')
    
    # Cache control
    parser.add_argument('--clear-cache', action='store_true', help='Clear the cache')
    
    # Output format
    parser.add_argument('--json', action='store_true', help='Output in JSON format')
    
    args = parser.parse_args()
    
    # Clear cache if requested
    if args.clear_cache:
        cache.clear()
        print("Cache cleared.")
        return
    
    # Single hostname lookup
    if args.lookup:
        result = get_support_group(args.lookup)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result['found']:
                print(f"Hostname: {result['hostname']}")
                print(f"Support Group: {result['support_group']}")
            else:
                print(f"Hostname '{args.lookup}' not found")
        return
    
    # Contact lookup
    if args.contacts:
        result = get_app_owners(args.contacts)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result['found']:
                print(f"Support Group: {result['support_group']}")
                contacts = result.get('contacts', {})
                if contacts.get('email_distros'):
                    print(f"Email: {contacts['email_distros']}")
                if contacts.get('individual_contacts'):
                    print(f"Contacts: {contacts['individual_contacts']}")
            else:
                print(f"Support group '{args.contacts}' not found")
        return
    
    # Single ticket processing
    if args.ticket:
        try:
            with open(args.ticket, 'r') as f:
                content = f.read()
            
            results = process_ticket(content)
            
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(format_results(results))
        
        except FileNotFoundError:
            print(f"Error: File '{args.ticket}' not found")
            sys.exit(1)
        except Exception as e:
            print(f"Error processing ticket: {str(e)}")
            sys.exit(1)
        return
    
    # Batch processing
    if args.batch:
        all_results = {}
        
        for pattern in args.batch:
            files = glob.glob(pattern)
            
            for file_path in files:
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    print(f"\nProcessing: {file_path}")
                    results = process_ticket(content)
                    all_results[file_path] = results
                    
                    if not args.json:
                        print(format_results(results))
                
                except Exception as e:
                    print(f"Error processing {file_path}: {str(e)}")
                    all_results[file_path] = {"status": "error", "message": str(e)}
        
        if args.json:
            print(json.dumps(all_results, indent=2))
        
        return
    
    # No arguments provided
    parser.print_help()

if __name__ == "__main__":
    main() 