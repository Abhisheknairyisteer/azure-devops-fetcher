from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Any, Optional
import traceback
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class FetchBoardsRequest(BaseModel):
    organization: str
    project: str
    pat: str
    work_item_type: Optional[str] = None
    assigned_to: Optional[str] = None

class FetchBoardsResponse(BaseModel):
    workItems: List[Dict[str, Any]]

@app.post("/fetch-azure-boards", response_model=FetchBoardsResponse)
def fetch_azure_boards(payload: FetchBoardsRequest):
    organization = payload.organization
    project = payload.project
    pat = payload.pat
    work_item_type = payload.work_item_type
    assigned_to = payload.assigned_to

    where_clauses = [f"[System.TeamProject] = '{project}'"]
    if work_item_type and work_item_type.lower() != 'all':
        where_clauses.append(f"[System.WorkItemType] = '{work_item_type}'")
    if assigned_to:
        where_clauses.append(f"[System.AssignedTo] CONTAINS '{assigned_to}'")

    where_string = " AND ".join(where_clauses)
    
    wiql_query = {
        "query": f"Select [System.Id], [System.Title], [System.State] From WorkItems WHERE {where_string}"
    }

    wiql_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/wiql?api-version=7.1-preview.2"
    logger.info(f"Posting WIQL to: {wiql_url} with query: {wiql_query['query']}")

    try:
        wiql_response = requests.post(
            wiql_url,
            json=wiql_query,
            auth=HTTPBasicAuth('', pat)
        )
        wiql_response.raise_for_status()

        data = wiql_response.json()
        work_item_ids = [str(item["id"]) for item in data.get("workItems", [])]

        if not work_item_ids:
            return {"workItems": [{"message": "No work items found matching your criteria."}]}

        detailed_workitems = []
        chunk_size = 100
        for i in range(0, len(work_item_ids), chunk_size):
            chunk_ids = work_item_ids[i:i + chunk_size]
            ids_str = ",".join(chunk_ids)
            workitems_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title,System.State,System.WorkItemType,System.AssignedTo&api-version=7.1-preview.2"

            workitems_response = requests.get(
                workitems_url,
                auth=HTTPBasicAuth('', pat)
            )
            workitems_response.raise_for_status()
            workitems_data = workitems_response.json()
            for item in workitems_data.get("value", []):
                detailed_workitems.append(item)

        simplified_results = []
        for item in detailed_workitems:
            fields = item.get("fields", {})
            
            # --- THIS IS THE FIX ---
            # It now checks if the 'AssignedTo' field is a dictionary or a string.
            assigned_to_field = fields.get("System.AssignedTo")
            assignee_name = "Unassigned" # Default value
            if isinstance(assigned_to_field, dict):
                # If it's a dictionary, get the displayName
                assignee_name = assigned_to_field.get("displayName", "Unassigned")
            elif isinstance(assigned_to_field, str):
                # If it's a string, just use the string
                assignee_name = assigned_to_field
            # If it's neither (e.g., None), it remains "Unassigned"

            simplified_results.append({
                "ID": item.get("id"),
                "Title": fields.get("System.Title", "N/A"),
                "State": fields.get("System.State", "N/A"),
                "Type": fields.get("System.WorkItemType", "N/A"),
                "AssignedTo": assignee_name
            })

        logger.info(f"Processed {len(simplified_results)} work items successfully.")
        return {"workItems": simplified_results}

    except Exception as e:
        logger.error("An error occurred during fetch_azure_boards execution:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))