from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Any
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

class FetchBoardsResponse(BaseModel):
    workItems: List[Dict[str, Any]]

@app.post("/fetch-azure-boards", response_model=FetchBoardsResponse)
def fetch_azure_boards(payload: FetchBoardsRequest):
    organization = payload.organization
    project = payload.project
    pat = payload.pat

    wiql_query = {
        "query": "Select [System.Id] From WorkItems"
    }

    wiql_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/wiql?api-version=7.1-preview.2"
    logger.info(f"Posting WIQL to: {wiql_url}")

    try:
        wiql_response = requests.post(
            wiql_url,
            json=wiql_query,
            auth=HTTPBasicAuth('', pat)
        )

        logger.info(f"WIQL Response: {wiql_response.status_code}, {wiql_response.text}")

        if wiql_response.status_code != 200:
            raise HTTPException(status_code=wiql_response.status_code, detail=wiql_response.text)

        data = wiql_response.json()
        work_item_ids = [str(item["id"]) for item in data.get("workItems", [])]

        if not work_item_ids:
            return {"workItems": []}

        detailed_workitems = []

        # Chunking to avoid URL length issues (max 100 per request)
        chunk_size = 100
        for i in range(0, len(work_item_ids), chunk_size):
            chunk_ids = work_item_ids[i:i + chunk_size]
            ids_str = ",".join(chunk_ids)
            workitems_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workitems?ids={ids_str}&api-version=7.1-preview.2"

            logger.info(f"Fetching work items from: {workitems_url}")

            workitems_response = requests.get(
                workitems_url,
                auth=HTTPBasicAuth('', pat)
            )

            logger.info(f"Workitems Response: {workitems_response.status_code}, {workitems_response.text}")

            if workitems_response.status_code != 200:
                raise HTTPException(status_code=workitems_response.status_code, detail=workitems_response.text)

            workitems_data = workitems_response.json()

            for item in workitems_data.get("value", []):
                detailed_workitems.append(item)

        logger.info(f"Fetched {len(detailed_workitems)} work items successfully.")
        return {"workItems": detailed_workitems}

    except Exception as e:
        logger.error("An error occurred during fetch_azure_boards execution:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
