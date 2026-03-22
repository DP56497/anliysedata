# -*- coding: utf-8 -*-
"""
CSV Data Analyzer Backend
Compatible with Flutter GetX App
"""

from fastapi import FastAPI, UploadFile, Form, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from starlette import status
import pandas as pd
import os
import uuid
from flask import Flask

# ------------------------------------------------------------
# Initialize FastAPI App
# ------------------------------------------------------------
app = FastAPI(title="CSV Data Analyzer API")

# ------------------------------------------------------------
# API Key Authentication
# ------------------------------------------------------------
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

SECRET_KEY = os.environ.get("MY_API_KEY")  # Render Secret Key


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API Key missing on server",
        )

    if api_key_header == SECRET_KEY:
        return api_key_header

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key"
    )


# ------------------------------------------------------------
# Upload Directory
# ------------------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ------------------------------------------------------------
# Upload & Analyze CSV
# ------------------------------------------------------------
@app.post("/upload-csv/", dependencies=[Depends(get_api_key)])
async def upload_csv(
    file: UploadFile,
    x_axis: str = Form(None),
    y_axis: str = Form(None),
):
    try:
        # Save uploaded CSV
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.csv")
        with open(file_path, "wb") as f:
            f.write(await file.read())

        # Load CSV
        df = pd.read_csv(file_path)

        # ---------- ORIGINAL SHAPE ----------
        original_rows = df.shape[0]
        original_columns = df.shape[1]

        # ---------- Missing Value Report BEFORE Cleaning ----------
        missing_value_report = (
            df.isnull().sum().rename("missing_count").to_frame()
        )
        missing_value_report["missing_percentage"] = (
            missing_value_report["missing_count"] / original_rows * 100
        )

        # ---------- CLEANING ----------
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        categorical_cols = df.select_dtypes(exclude=["number"]).columns.tolist()

        cleaning_actions = []

        # Fill categorical missing values
        for col in categorical_cols:
            null_pct = df[col].isnull().mean() * 100

            if null_pct > 0:
                if null_pct < 20:
                    df[col].fillna(df[col].mode()[0], inplace=True)
                    cleaning_actions.append({
                        "column": col,
                        "type": "categorical",
                        "action": "filled_with_mode",
                        "missing_percentage": round(null_pct, 2)
                    })
                else:
                    df.drop(col, axis=1, inplace=True)
                    cleaning_actions.append({
                        "column": col,
                        "type": "categorical",
                        "action": "column_removed_high_missing",
                        "missing_percentage": round(null_pct, 2)
                    })

        # Fill numeric missing values
        for col in numeric_cols:
            null_pct = df[col].isnull().mean() * 100

            if null_pct > 0:
                if null_pct < 20:
                    df[col].fillna(df[col].mean(), inplace=True)
                    cleaning_actions.append({
                        "column": col,
                        "type": "numeric",
                        "action": "filled_with_mean",
                        "missing_percentage": round(null_pct, 2)
                    })
                else:
                    df.drop(col, axis=1, inplace=True)
                    cleaning_actions.append({
                        "column": col,
                        "type": "numeric",
                        "action": "column_removed_high_missing",
                        "missing_percentage": round(null_pct, 2)
                    })

        # ---------- UPDATED COLUMN LISTS ----------
        updated_numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        updated_categorical_cols = df.select_dtypes(exclude=["number"]).columns.tolist()

        # ---------- AXIS SELECTION ----------
        if not x_axis or x_axis not in df.columns:
            x_axis = df.columns[0] if len(df.columns) else "N/A"

        if not y_axis or y_axis not in df.columns:
            y_axis = updated_numeric_cols[0] if updated_numeric_cols else None

        # ---------- STATS ----------
        stats = {}
        if updated_numeric_cols and y_axis in updated_numeric_cols:
            df[y_axis] = pd.to_numeric(df[y_axis], errors="ignore")
            stats = df.describe().to_dict()

        # ---------- REAL ROW DATA ----------
        preview_rows = df.head(200).to_dict(orient="records")

        # ---------- ROWS REMOVED ----------
        final_rows = df.shape[0]
        removed_rows_count = original_rows - final_rows

        # ---------- RESPONSE ----------
        response_data = {
            "message": "CSV uploaded successfully",

            # Columns
            "available_columns": df.columns.tolist(),
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "updated_numeric_columns": updated_numeric_cols,
            "updated_categorical_columns": updated_categorical_cols,

            # Missing Value Summary
            "missing_value_report": missing_value_report.to_dict(orient="index"),

            # Cleaning Actions (Very Important)
            "cleaning_actions": cleaning_actions,
            "removed_rows_count": removed_rows_count,

            # Axis defaults
            "x_axis": x_axis,
            "y_axis": y_axis,

            # Stats for numeric columns
            "stats": stats,

            # Counts
            "rows_before_cleaning": original_rows,
            "rows_after_cleaning": final_rows,
            "columns_before_cleaning": original_columns,
            "columns_after_cleaning": df.shape[1],

            # Actual data rows
            "rows": preview_rows,
        }

        return JSONResponse(content=response_data)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)
