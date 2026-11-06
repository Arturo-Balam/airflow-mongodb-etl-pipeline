"""Dashboard entry point. For now it only checks the MongoDB connection."""

import os

import pandas as pd
import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError

st.set_page_config(page_title="ETL Pipeline Dashboard", layout="wide")


@st.cache_resource
def get_db():
    client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000)
    return client[os.environ["MONGO_DB"]]


st.title("ETL Pipeline Dashboard")

try:
    db = get_db()
    db.command("ping")
except PyMongoError as exc:
    st.error(f"Cannot reach MongoDB: {exc}")
    st.stop()

st.success("Connected to MongoDB")

collections = sorted(db.list_collection_names())
if collections:
    counts = pd.DataFrame(
        {
            "collection": collections,
            "documents": [db[c].count_documents({}) for c in collections],
        }
    )
    st.subheader("Collections")
    st.dataframe(counts, hide_index=True, use_container_width=True)
else:
    st.info("No collections yet. Trigger a DAG in Airflow (http://localhost:8080).")
