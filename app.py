import json
import os
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta
from functools import wraps
import auth

# try to solve Azure issue
from urllib.parse import urlencode

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "your_super_secret_key")
bcrypt = Bcrypt(app)


#######################################################
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


#######################################################
# Database configuration
DB_PATH = "fieldforce.db"
COROMANDEL_COMPANY_CODE = 7007


def get_db_connection():
    global DB_PATH
    if os.environ.get("WEBSITE_INSTANCE_ID"):  # Running on Azure
        # DB_PATH = "/mnt/data/" + DB_PATH
        DB_PATH = "/home/site/data/fieldforce.db"
    _db_connection = sqlite3.connect(DB_PATH)
    _db_connection.row_factory = sqlite3.Row
    return _db_connection


def dict_from_row(row):
    return dict(zip(row.keys(), row))


# Get competitor codes dynamically or use fallback
def get_competitor_codes():
    """Get actual competitor company codes from database"""
    try:
        conn = get_db_connection()
        query = """
            SELECT company_code, company_name
            FROM dim_companies
            WHERE company_name IN ('BAYER CROP SCIENCE', 'UPL LIMITED', 'SYNGENTA INDIA LTD')
            OR company_code IN (7002, 7025, 7024)
        """
        results = conn.execute(query).fetchall()

        competitors = {}
        for row in results:
            name = row["company_name"].upper()
            if "BAYER" in name:
                competitors["BAYER"] = row["company_code"]
            elif "UPL" in name:
                competitors["UPL"] = row["company_code"]
            elif "SYNGENTA" in name:
                competitors["SYNGENTA"] = row["company_code"]

        # Fallback to default codes if not found
        if "BAYER" not in competitors:
            competitors["BAYER"] = 7002
        if "UPL" not in competitors:
            competitors["UPL"] = 7025
        if "SYNGENTA" not in competitors:
            competitors["SYNGENTA"] = 7024

        return competitors
    except Exception as e:
        print(f"Error loading competitor codes: {e}")
        # Fallback
        return {"BAYER": 7002, "UPL": 7025, "SYNGENTA": 7024}


COMPETITORS = get_competitor_codes()


def parse_date_filter(date_filter):
    """Parse date filter and return start_date, end_date"""
    end_date = datetime.now()

    if date_filter == "all":
        return None, None
    elif date_filter.isdigit():
        start_date = end_date - timedelta(days=int(date_filter))
        return start_date, end_date
    elif "-" in date_filter:  # Custom date range: "2024-01-01,2024-12-31"
        dates = date_filter.split(",")
        return dates[0], dates[1]
    else:
        start_date = end_date - timedelta(days=30)
        return start_date, end_date


# ==================== FILTER OPTIONS APIs ====================


@app.route("/api/filters/crops")
@login_required
def get_crop_options():
    conn = get_db_connection()
    try:
        query = """
            SELECT DISTINCT dc.crop_code, dc.crop_name, dc.crop_type
            FROM dim_crops dc
            JOIN fact_conversation_entities fce ON dc.crop_code = fce.entity_code
            WHERE fce.entity_type = 'crop'
            AND dc.crop_name != '_OTHERS (PLEASE SPECIFY)'
            AND dc.crop_name != 'No Crop'
            ORDER BY dc.crop_name
        """
        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/filters/crop-types")
@login_required
def get_crop_type_options():
    conn = get_db_connection()
    try:
        query = """
            SELECT DISTINCT crop_type
            FROM dim_crops
            WHERE crop_type IS NOT NULL
            AND crop_type != '(blank)'
            AND crop_type != 'No Crop'
            ORDER BY crop_type
        """
        results = conn.execute(query).fetchall()
        return jsonify([row["crop_type"] for row in results])
    finally:
        conn.close()


# ==================== HOME MODULE APIs ====================


@app.route("/api/home/kpis")
@login_required
def get_home_kpis():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")
    crop_filter = request.args.get("crop", "all")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        date_clause = ""
        params = []
        if start_date and end_date:
            date_clause = "AND fc.created_at >= ? AND fc.created_at <= ?"
            params = [start_date, end_date]

        # Alert Count KPI
        alert_query = f"""
            SELECT COUNT(*) as alert_count
            FROM fact_conversation_metrics fcm
            JOIN fact_conversations fc ON fcm.conversation_id = fc.conversation_id
            WHERE fcm.alert_flag = 1 {date_clause}
        """

        # Market Health KPI
        health_query = f"""
            SELECT AVG(CASE
                WHEN overall_sentiment = 'positive' THEN 100
                WHEN overall_sentiment = 'neutral' THEN 50
                WHEN overall_sentiment = 'negative' THEN 0
            END) as health_score
            FROM fact_conversation_semantics fcs
            JOIN fact_conversations fc ON fcs.conversation_id = fc.conversation_id
            WHERE 1=1 {date_clause}
        """

        # Activity KPI
        activity_query = f"""
            SELECT COUNT(*) as activity_count
            FROM fact_conversations fc
            WHERE 1=1 {date_clause}
        """

        alerts = conn.execute(alert_query, params).fetchone()
        health = conn.execute(health_query, params).fetchone()
        activity = conn.execute(activity_query, params).fetchone()

        return jsonify(
            {
                "alert_count": alerts["alert_count"] or 0,
                "market_health": round(health["health_score"] or 50, 1),
                "activity_count": activity["activity_count"] or 0,
            }
        )
    finally:
        conn.close()


@app.route("/api/home/volume-sentiment")
@login_required
def get_volume_sentiment():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    COUNT(*) as volume,
                    AVG(CASE
                        WHEN fcs.overall_sentiment = 'positive' THEN 1
                        WHEN fcs.overall_sentiment = 'neutral' THEN 0
                        WHEN fcs.overall_sentiment = 'negative' THEN -1
                    END) as sentiment_score
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                WHERE fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at)
                ORDER BY date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    COUNT(*) as volume,
                    AVG(CASE
                        WHEN fcs.overall_sentiment = 'positive' THEN 1
                        WHEN fcs.overall_sentiment = 'neutral' THEN 0
                        WHEN fcs.overall_sentiment = 'negative' THEN -1
                    END) as sentiment_score
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                GROUP BY DATE(fc.created_at)
                ORDER BY date
            """
            results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["date"] for row in results],
                "volume": [row["volume"] for row in results],
                "sentiment": [
                    round(row["sentiment_score"] * 100, 2)
                    if row["sentiment_score"]
                    else 0
                    for row in results
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/home/conversation-distribution")
@login_required
def get_conversation_distribution():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                primary_topic,
                COUNT(*) as count
            FROM fact_conversation_semantics
            GROUP BY primary_topic
            ORDER BY count DESC
            LIMIT 5
        """

        results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["primary_topic"] for row in results],
                "data": [row["count"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/home/market-share")
@login_required
def get_market_share():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                dc.company_name,
                COUNT(DISTINCT fce.conversation_id) as mentions
            FROM fact_conversation_entities fce
            JOIN dim_brands db ON fce.entity_code = db.brand_code
            JOIN dim_companies dc ON db.company_code = dc.company_code
            WHERE fce.entity_type = 'brand'
            AND dc.company_code IN (?, ?, ?, ?)
            GROUP BY dc.company_name
            ORDER BY mentions DESC
        """

        results = conn.execute(
            query,
            (
                COROMANDEL_COMPANY_CODE,
                COMPETITORS["BAYER"],
                COMPETITORS["UPL"],
                COMPETITORS["SYNGENTA"],
            ),
        ).fetchall()

        return jsonify(
            {
                "labels": [row["company_name"] for row in results],
                "data": [row["mentions"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/home/competitive-position")
@login_required
def get_competitive_position():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                dc.company_name as brand,
                COUNT(DISTINCT fce.conversation_id) as mentions,
                ROUND(COUNT(DISTINCT fce.conversation_id) * 100.0 /
                    (SELECT COUNT(DISTINCT conversation_id) FROM fact_conversation_entities WHERE entity_type = 'brand'), 1) as share,
                0 as score
            FROM fact_conversation_entities fce
            JOIN dim_brands db ON fce.entity_code = db.brand_code
            JOIN dim_companies dc ON db.company_code = dc.company_code
            WHERE fce.entity_type = 'brand'
            AND dc.company_code IN (?, ?, ?, ?)
            GROUP BY dc.company_name
            ORDER BY share DESC
            LIMIT 3
        """

        results = conn.execute(
            query,
            (
                COROMANDEL_COMPANY_CODE,
                COMPETITORS["BAYER"],
                COMPETITORS["UPL"],
                COMPETITORS["SYNGENTA"],
            ),
        ).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/home/conversation-drivers")
@login_required
def get_conversation_drivers():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                intent as driver,
                COUNT(*) as count
            FROM fact_conversation_semantics
            GROUP BY intent
            ORDER BY count DESC
            LIMIT 10
        """

        results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["driver"] for row in results],
                "data": [row["count"] for row in results],
            }
        )
    finally:
        conn.close()


# ==================== MARKETING MODULE APIs ====================


@app.route("/api/marketing/brand-health-trend")
@login_required
def get_brand_health_trend():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    COUNT(*) as volume,
                    50 as health
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                JOIN dim_brands db ON fce.entity_code = db.brand_code
                WHERE db.company_code = ?
                AND fce.entity_type = 'brand'
                AND fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at)
                ORDER BY date
            """
            results = conn.execute(
                query, (COROMANDEL_COMPANY_CODE, start_date, end_date)
            ).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    COUNT(*) as volume,
                    50 as health
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                JOIN dim_brands db ON fce.entity_code = db.brand_code
                WHERE db.company_code = ?
                AND fce.entity_type = 'brand'
                GROUP BY DATE(fc.created_at)
                ORDER BY date
            """
            results = conn.execute(query, (COROMANDEL_COMPANY_CODE,)).fetchall()

        return jsonify(
            {
                "labels": [row["date"] for row in results],
                "volume": [row["volume"] for row in results],
                "health": [
                    round(row["health"], 2) if row["health"] is not None else 50
                    for row in results
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/marketing/conv-volume-by-topic")
@login_required
def get_conv_volume_by_topic():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    fcs.primary_topic,
                    COUNT(*) as count
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                WHERE fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at), fcs.primary_topic
                ORDER BY date, count DESC
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    fcs.primary_topic,
                    COUNT(*) as count
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                GROUP BY DATE(fc.created_at), fcs.primary_topic
                ORDER BY date, count DESC
            """
            results = conn.execute(query).fetchall()

        # Reorganize data
        dates = sorted(list(set([row["date"] for row in results])))
        topics = list(set([row["primary_topic"] for row in results]))[:5]  # Top 5 topics

        datasets = {}
        for topic in topics:
            datasets[topic] = [0] * len(dates)

        for row in results:
            if row["primary_topic"] in topics:
                date_idx = dates.index(row["date"])
                datasets[row["primary_topic"]][date_idx] = row["count"]

        return jsonify(
            {
                "labels": dates,
                "datasets": [
                    {"label": topic, "data": data} for topic, data in datasets.items()
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/marketing/brand-keywords")
@login_required
def get_brand_keywords():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                db.brand_name as word,
                COUNT(*) as weight
            FROM fact_conversation_entities fce
            JOIN dim_brands db ON fce.entity_code = db.brand_code
            WHERE fce.entity_type = 'brand'
            AND db.company_code = ?
            GROUP BY db.brand_name
            ORDER BY weight DESC
            LIMIT 50
        """

        results = conn.execute(query, (COROMANDEL_COMPANY_CODE,)).fetchall()

        return jsonify(
            [{"text": row["word"], "size": row["weight"]} for row in results]
        )
    finally:
        conn.close()


@app.route("/api/marketing/market-share-trend")
@login_required
def get_market_share_trend():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    dc.company_name,
                    COUNT(DISTINCT fce.conversation_id) as mentions
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                JOIN dim_brands db ON fce.entity_code = db.brand_code
                JOIN dim_companies dc ON db.company_code = dc.company_code
                WHERE fce.entity_type = 'brand'
                AND dc.company_code IN (?, ?, ?, ?)
                AND fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at), dc.company_name
                ORDER BY date
            """
            results = conn.execute(
                query,
                (
                    COROMANDEL_COMPANY_CODE,
                    COMPETITORS["BAYER"],
                    COMPETITORS["UPL"],
                    COMPETITORS["SYNGENTA"],
                    start_date,
                    end_date,
                ),
            ).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    dc.company_name,
                    COUNT(DISTINCT fce.conversation_id) as mentions
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                JOIN dim_brands db ON fce.entity_code = db.brand_code
                JOIN dim_companies dc ON db.company_code = dc.company_code
                WHERE fce.entity_type = 'brand'
                AND dc.company_code IN (?, ?, ?, ?)
                GROUP BY DATE(fc.created_at), dc.company_name
                ORDER BY date
            """
            results = conn.execute(
                query,
                (
                    COROMANDEL_COMPANY_CODE,
                    COMPETITORS["BAYER"],
                    COMPETITORS["UPL"],
                    COMPETITORS["SYNGENTA"],
                ),
            ).fetchall()

        dates = sorted(list(set([row["date"] for row in results])))
        companies = list(set([row["company_name"] for row in results]))

        datasets = {}
        for company in companies:
            datasets[company] = [0] * len(dates)

        for row in results:
            date_idx = dates.index(row["date"])
            datasets[row["company_name"]][date_idx] = row["mentions"]

        return jsonify(
            {
                "labels": dates,
                "datasets": [
                    {"label": company, "data": data}
                    for company, data in datasets.items()
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/marketing/competitive-landscape")
@login_required
def get_competitive_landscape():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                dc.company_name,
                COUNT(DISTINCT fce.conversation_id) as x,
                0 as y,
                COUNT(DISTINCT fce.conversation_id) as r
            FROM fact_conversation_entities fce
            JOIN dim_brands db ON fce.entity_code = db.brand_code
            JOIN dim_companies dc ON db.company_code = dc.company_code
            WHERE fce.entity_type = 'brand'
            AND dc.company_code IN (?, ?, ?, ?)
            GROUP BY dc.company_name
        """

        results = conn.execute(
            query,
            (
                COROMANDEL_COMPANY_CODE,
                COMPETITORS["BAYER"],
                COMPETITORS["UPL"],
                COMPETITORS["SYNGENTA"],
            ),
        ).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/marketing/sentiment-by-competitor")
@login_required
def get_sentiment_by_competitor():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    dc.company_name,
                    50 as sentiment
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                JOIN dim_brands db ON fce.entity_code = db.brand_code
                JOIN dim_companies dc ON db.company_code = dc.company_code
                WHERE fce.entity_type = 'brand'
                AND dc.company_code IN (?, ?, ?, ?)
                AND fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at), dc.company_name
                ORDER BY date
            """
            results = conn.execute(
                query,
                (
                    COROMANDEL_COMPANY_CODE,
                    COMPETITORS["BAYER"],
                    COMPETITORS["UPL"],
                    COMPETITORS["SYNGENTA"],
                    start_date,
                    end_date,
                ),
            ).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    dc.company_name,
                    50 as sentiment
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                JOIN dim_brands db ON fce.entity_code = db.brand_code
                JOIN dim_companies dc ON db.company_code = dc.company_code
                WHERE fce.entity_type = 'brand'
                AND dc.company_code IN (?, ?, ?, ?)
                AND fce.overall_sentiment IS NOT NULL
                GROUP BY DATE(fc.created_at), dc.company_name
                ORDER BY date
            """
            results = conn.execute(
                query,
                (
                    COROMANDEL_COMPANY_CODE,
                    COMPETITORS["BAYER"],
                    COMPETITORS["UPL"],
                    COMPETITORS["SYNGENTA"],
                ),
            ).fetchall()

        # Get all unique dates and companies
        dates = sorted(list(set([row["date"] for row in results])))

        # Create datasets for each company
        company_data = {}
        for row in results:
            if row["company_name"] not in company_data:
                company_data[row["company_name"]] = {}
            company_data[row["company_name"]][row["date"]] = (
                round(row["sentiment"], 2) if row["sentiment"] is not None else 50
            )

        # Fill in missing dates with null or previous value
        datasets = []
        for company_name, data in company_data.items():
            dataset_values = []
            for date in dates:
                dataset_values.append(data.get(date, None))
            datasets.append({"label": company_name, "data": dataset_values})

        return jsonify({"labels": dates, "datasets": datasets})
    finally:
        conn.close()


@app.route("/api/marketing/brand-crop-association")
@login_required
def get_brand_crop_association():
    conn = get_db_connection()

    try:
        # Get ALL Rallis brands with crop associations
        query = """
            SELECT
                db.brand_name as parent,
                mbcm.crop_name as label,
                mbcm.co_mentions as value
            FROM mart_brand_crop_matrix mbcm
            JOIN dim_brands db ON mbcm.brand_code = db.brand_code
            WHERE db.company_code = ?
            AND mbcm.co_mentions > 0
            ORDER BY db.brand_name, mbcm.co_mentions DESC
        """

        results = conn.execute(query, (COROMANDEL_COMPANY_CODE,)).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


# ==================== OPERATIONS MODULE APIs ====================


@app.route("/api/operations/urgent-issues")
@login_required
def get_urgent_issues():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                fc.conversation_id,
                fc.created_at,
                fc.user_text,
                fcs.urgency,
                fcs.primary_topic,
                fcs.overall_sentiment
            FROM fact_conversations fc
            JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
            WHERE fcs.urgency IN ('high', 'critical')
            ORDER BY fc.created_at DESC
            LIMIT 50
        """

        results = conn.execute(query).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/operations/demand-signal-trend")
@login_required
def get_demand_signal_trend():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    COUNT(CASE WHEN fcs.intent IN ('purchase', 'request_info', 'seek_advice') THEN 1 END) as demand_signal
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                WHERE fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at)
                ORDER BY date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    COUNT(CASE WHEN fcs.intent IN ('purchase', 'request_info', 'seek_advice') THEN 1 END) as demand_signal
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                GROUP BY DATE(fc.created_at)
                ORDER BY date
            """
            results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["date"] for row in results],
                "data": [row["demand_signal"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/operations/demand-change-alert")
@login_required
def get_demand_change_alert():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                dc.crop_name,
                COUNT(*) as current_demand,
                'stable' as trend,
                0 as change_pct
            FROM fact_conversation_entities fce
            JOIN dim_crops dc ON fce.entity_code = dc.crop_code
            WHERE fce.entity_type = 'crop'
            GROUP BY dc.crop_name
            ORDER BY current_demand DESC
            LIMIT 10
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/operations/crop-pest-heatmap")
@login_required
def get_crop_pest_heatmap():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                crop_name,
                pest_name,
                co_mentions
            FROM mart_crop_pest_matrix
            ORDER BY co_mentions DESC
            LIMIT 100
        """

        results = conn.execute(query).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/operations/problem-trend")
@login_required
def get_problem_trend():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    fcs.primary_topic as topic,
                    COUNT(*) as count
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                WHERE fcs.primary_topic IN ('pest', 'disease', 'weed', 'crop_damage')
                AND fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at), fcs.primary_topic
                ORDER BY date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    fcs.primary_topic as topic,
                    COUNT(*) as count
                FROM fact_conversations fc
                JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
                WHERE fcs.primary_topic IN ('pest', 'disease', 'weed', 'crop_damage')
                GROUP BY DATE(fc.created_at), fcs.primary_topic
                ORDER BY date
            """
            results = conn.execute(query).fetchall()

        dates = sorted(list(set([row["date"] for row in results])))
        topics = ["pest", "disease", "weed", "crop_damage"]

        datasets = {}
        for topic in topics:
            datasets[topic] = [0] * len(dates)

        for row in results:
            if row["topic"] in topics and row["date"] in dates:
                date_idx = dates.index(row["date"])
                datasets[row["topic"]][date_idx] = row["count"]

        return jsonify(
            {
                "labels": dates,
                "datasets": [
                    {"label": topic.capitalize(), "data": data}
                    for topic, data in datasets.items()
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/operations/problem-sentiment")
def get_problem_sentiment():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                fcs.primary_topic as topic,
                fcs.overall_sentiment as sentiment,
                COUNT(*) as count
            FROM fact_conversation_semantics fcs
            WHERE fcs.primary_topic IN ('pest', 'disease', 'weed')
            GROUP BY fcs.primary_topic, fcs.overall_sentiment
            ORDER BY count DESC
        """

        results = conn.execute(query).fetchall()

        topics = sorted(list(set([row["topic"] for row in results])))

        positive = [0] * len(topics)
        neutral = [0] * len(topics)
        negative = [0] * len(topics)

        for row in results:
            if row["topic"] in topics:
                idx = topics.index(row["topic"])
                if row["sentiment"] == "positive":
                    positive[idx] = row["count"]
                elif row["sentiment"] == "neutral":
                    neutral[idx] = row["count"]
                elif row["sentiment"] == "negative":
                    negative[idx] = row["count"]

        return jsonify(
            {
                "labels": topics,
                "datasets": [
                    {"label": "Positive", "data": positive},
                    {"label": "Neutral", "data": neutral},
                    {"label": "Negative", "data": negative},
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/operations/crop-keywords")
def get_crop_keywords():
    conn = get_db_connection()

    try:
        # Get all crops with their mention counts
        query = """
            SELECT
                dc.crop_name as word,
                COUNT(DISTINCT fce.conversation_id) as weight
            FROM fact_conversation_entities fce
            JOIN dim_crops dc ON fce.entity_code = dc.crop_code
            WHERE fce.entity_type = 'crop'
            AND dc.crop_name NOT IN ('_OTHERS (PLEASE SPECIFY)', 'No Crop')
            AND dc.crop_name IS NOT NULL
            GROUP BY dc.crop_name
            ORDER BY weight DESC
            LIMIT 50
        """

        results = conn.execute(query).fetchall()

        if len(results) == 0:
            # Fallback: get from dim_crops directly
            query2 = """
                SELECT DISTINCT crop_name as word, 1 as weight
                FROM dim_crops
                WHERE crop_name NOT IN ('_OTHERS (PLEASE SPECIFY)', 'No Crop')
                AND crop_name IS NOT NULL
                AND crop_type != '(blank)'
                LIMIT 50
            """
            results = conn.execute(query2).fetchall()

        return jsonify(
            [
                {"text": row["word"], "size": row["weight"]}
                for row in results
                if row["word"]
            ]
        )
    finally:
        conn.close()


@app.route("/api/operations/solution-flow")
def get_solution_flow():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                crop_name,
                pest_name,
                brand_name,
                flow_count
            FROM mart_crop_pest_brand_flow
            ORDER BY flow_count DESC
            LIMIT 50
        """

        results = conn.execute(query).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/operations/solution-effectiveness")
def get_solution_effectiveness():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                db.brand_name as solution,
                COUNT(DISTINCT fce.conversation_id) as effectiveness
            FROM fact_conversation_entities fce
            JOIN dim_brands db ON fce.entity_code = db.brand_code
            WHERE fce.entity_type = 'brand'
            GROUP BY db.brand_name
            ORDER BY effectiveness DESC
            LIMIT 10
        """

        results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["solution"] for row in results],
                "data": [row["effectiveness"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/operations/solution-sentiment")
def get_solution_sentiment():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    50 as sentiment
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                WHERE fce.entity_type = 'brand'
                AND fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at)
                HAVING COUNT(*) > 0
                ORDER BY date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    50 as sentiment
                FROM fact_conversations fc
                JOIN fact_conversation_entities fce ON fc.conversation_id = fce.conversation_id
                WHERE fce.entity_type = 'brand'
                GROUP BY DATE(fc.created_at)
                HAVING COUNT(*) > 0
                ORDER BY date
            """
            results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["date"] for row in results],
                "data": [
                    round(row["sentiment"], 2) if row["sentiment"] is not None else None
                    for row in results
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/operations/sentiment-by-crop")
def get_sentiment_by_crop():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                dc.crop_name,
                COUNT(*) as count
            FROM fact_conversation_entities fce
            JOIN dim_crops dc ON fce.entity_code = dc.crop_code
            WHERE fce.entity_type = 'crop'
            AND dc.crop_name NOT IN ('_OTHERS (PLEASE SPECIFY)', 'No Crop')
            GROUP BY dc.crop_name
            ORDER BY count DESC
        """

        results = conn.execute(query).fetchall()

        # Get top 10 crops by total mentions
        crop_totals = {}
        for row in results:
            if row["crop_name"] not in crop_totals:
                crop_totals[row["crop_name"]] = 0
            crop_totals[row["crop_name"]] += row["count"]

        top_crops = sorted(crop_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        crops = [c[0] for c in top_crops]

        positive = [0] * len(crops)
        neutral = [0] * len(crops)
        negative = [0] * len(crops)

        return jsonify(
            {
                "labels": crops,
                "datasets": [
                    {"label": "Positive", "data": positive},
                    {"label": "Neutral", "data": neutral},
                    {"label": "Negative", "data": negative},
                ],
            }
        )
    finally:
        conn.close()


# ==================== ENGAGEMENT MODULE APIs ====================


@app.route("/api/engagement/conv-by-region")
def get_conv_by_region():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                du.district as region,
                COUNT(*) as count
            FROM fact_conversations fc
            JOIN dim_user du ON fc.user_id = du.user_id
            GROUP BY du.district
            ORDER BY count DESC
            LIMIT 20
        """

        results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["region"] for row in results],
                "data": [row["count"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/engagement/team-urgency")
def get_team_urgency():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                urgency,
                COUNT(*) as count
            FROM fact_conversation_semantics
            GROUP BY urgency
        """

        results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["urgency"] for row in results],
                "data": [row["count"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/engagement/team-intent")
def get_team_intent():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                intent,
                COUNT(*) as count
            FROM fact_conversation_semantics
            GROUP BY intent
            ORDER BY count DESC
            LIMIT 5
        """

        results = conn.execute(query).fetchall()

        return jsonify(
            {
                "labels": [row["intent"] for row in results],
                "data": [row["count"] for row in results],
            }
        )
    finally:
        conn.close()


@app.route("/api/engagement/quality-by-region")
def get_quality_by_region():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                du.district as region,
                fcs.overall_sentiment as sentiment,
                COUNT(*) as count
            FROM fact_conversations fc
            JOIN dim_user du ON fc.user_id = du.user_id
            JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
            GROUP BY du.district, fcs.overall_sentiment
            ORDER BY count DESC
            LIMIT 60
        """

        results = conn.execute(query).fetchall()

        regions = sorted(list(set([row["region"] for row in results])))[:10]

        positive = [0] * len(regions)
        neutral = [0] * len(regions)
        negative = [0] * len(regions)

        for row in results:
            if row["region"] in regions:
                idx = regions.index(row["region"])
                if row["sentiment"] == "positive":
                    positive[idx] = row["count"]
                elif row["sentiment"] == "neutral":
                    neutral[idx] = row["count"]
                elif row["sentiment"] == "negative":
                    negative[idx] = row["count"]

        return jsonify(
            {
                "labels": regions,
                "datasets": [
                    {"label": "Positive", "data": positive},
                    {"label": "Neutral", "data": neutral},
                    {"label": "Negative", "data": negative},
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/engagement/agent-scorecard")
def get_agent_scorecard():
    conn = get_db_connection()

    try:
        # Simulated agent performance data
        query = """
            SELECT
                du.full_name as agent_name,
                COUNT(fc.conversation_id) as total_convs,
                AVG(CASE
                    WHEN fcs.overall_sentiment = 'positive' THEN 100
                    WHEN fcs.overall_sentiment = 'neutral' THEN 50
                    WHEN fcs.overall_sentiment = 'negative' THEN 0
                END) as avg_sentiment,
                COUNT(CASE WHEN fcs.urgency IN ('high', 'critical') THEN 1 END) as urgent_handled
            FROM fact_conversations fc
            JOIN dim_user du ON fc.user_id = du.user_id
            JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
            GROUP BY du.full_name
            ORDER BY total_convs DESC
            LIMIT 20
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/engagement/agent-leaderboard")
def get_agent_leaderboard():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                du.full_name as agent_name,
                COUNT(fc.conversation_id) as conversations,
                AVG(CASE
                    WHEN fcs.overall_sentiment = 'positive' THEN 3
                    WHEN fcs.overall_sentiment = 'neutral' THEN 2
                    WHEN fcs.overall_sentiment = 'negative' THEN 1
                END) as performance_score
            FROM fact_conversations fc
            JOIN dim_user du ON fc.user_id = du.user_id
            JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
            GROUP BY du.full_name
            ORDER BY performance_score DESC, conversations DESC
            LIMIT 10
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/engagement/agent-perf-trend")
def get_agent_perf_trend():
    conn = get_db_connection()
    date_filter = request.args.get("date", "30")

    try:
        start_date, end_date = parse_date_filter(date_filter)

        if start_date and end_date:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    du.full_name as agent,
                    COUNT(*) as conversations
                FROM fact_conversations fc
                JOIN dim_user du ON fc.user_id = du.user_id
                WHERE fc.created_at >= ? AND fc.created_at <= ?
                GROUP BY DATE(fc.created_at), du.full_name
                ORDER BY date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
        else:
            query = """
                SELECT
                    DATE(fc.created_at) as date,
                    du.full_name as agent,
                    COUNT(*) as conversations
                FROM fact_conversations fc
                JOIN dim_user du ON fc.user_id = du.user_id
                GROUP BY DATE(fc.created_at), du.full_name
                ORDER BY date
            """
            results = conn.execute(query).fetchall()

        dates = sorted(list(set([row["date"] for row in results])))
        agents = list(set([row["agent"] for row in results]))[:5]  # Top 5 agents

        datasets = {}
        for agent in agents:
            datasets[agent] = [0] * len(dates)

        for row in results:
            if row["agent"] in agents and row["date"] in dates:
                date_idx = dates.index(row["date"])
                datasets[row["agent"]][date_idx] = row["conversations"]

        return jsonify(
            {
                "labels": dates,
                "datasets": [
                    {"label": agent, "data": data} for agent, data in datasets.items()
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/engagement/field-leaders")
def get_field_leaders():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                du.full_name as name,
                COUNT(fc.conversation_id) as x,
                AVG(CASE
                    WHEN fcs.overall_sentiment = 'positive' THEN 100
                    WHEN fcs.overall_sentiment = 'neutral' THEN 50
                    WHEN fcs.overall_sentiment = 'negative' THEN 0
                END) as y,
                COUNT(fc.conversation_id) as r
            FROM fact_conversations fc
            JOIN dim_user du ON fc.user_id = du.user_id
            JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
            GROUP BY du.full_name
            ORDER BY x DESC
            LIMIT 20
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/engagement/sentiment-by-entity")
def get_sentiment_by_entity():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                fce.entity_type,
                COUNT(*) as count
            FROM fact_conversation_entities fce
            WHERE fce.entity_type IN ('brand', 'crop', 'pest')
            GROUP BY fce.entity_type
            ORDER BY count DESC
        """

        results = conn.execute(query).fetchall()

        entities = sorted(list(set([row["entity_type"] for row in results])))

        positive = [0] * len(entities)
        neutral = [0] * len(entities)
        negative = [0] * len(entities)

        return jsonify(
            {
                "labels": [e.capitalize() for e in entities],
                "datasets": [
                    {"label": "Positive", "data": positive},
                    {"label": "Neutral", "data": neutral},
                    {"label": "Negative", "data": negative},
                ],
            }
        )
    finally:
        conn.close()


@app.route("/api/engagement/topic-distribution")
def get_topic_distribution():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                primary_topic as label,
                COUNT(*) as value
            FROM fact_conversation_semantics
            GROUP BY primary_topic
            ORDER BY value DESC
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/engagement/training-needs")
def get_training_needs():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                du.full_name as agent_name,
                fcs.primary_topic as weak_area,
                COUNT(CASE WHEN fcs.overall_sentiment = 'negative' THEN 1 END) as negative_count,
                'Needs training in ' || fcs.primary_topic as recommendation
            FROM fact_conversations fc
            JOIN dim_user du ON fc.user_id = du.user_id
            JOIN fact_conversation_semantics fcs ON fc.conversation_id = fcs.conversation_id
            WHERE fcs.overall_sentiment = 'negative'
            GROUP BY du.full_name, fcs.primary_topic
            HAVING COUNT(CASE WHEN fcs.overall_sentiment = 'negative' THEN 1 END) > 2
            ORDER BY negative_count DESC
            LIMIT 20
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


# ==================== ADMIN MODULE APIs ====================


@app.route("/api/admin/users")
def get_users():
    conn = get_db_connection()

    try:
        query = "SELECT * FROM dim_dashboard_users"
        results = conn.execute(query).fetchall()

        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/admin/user-activity-log")
def get_user_activity_log():
    conn = get_db_connection()

    try:
        query = """
            SELECT
                du.full_name as user_name,
                COUNT(fc.conversation_id) as activity_count,
                MAX(fc.created_at) as last_active,
                du.district as location
            FROM dim_user du
            LEFT JOIN fact_conversations fc ON du.user_id = fc.user_id
            GROUP BY du.full_name, du.district
            ORDER BY activity_count DESC
            LIMIT 50
        """

        results = conn.execute(query).fetchall()
        return jsonify([dict_from_row(row) for row in results])
    finally:
        conn.close()


@app.route("/api/admin/completeness-kpi")
def get_completeness_kpi():
    conn = get_db_connection()

    try:
        # Calculate data completeness metrics
        total_convs = conn.execute(
            "SELECT COUNT(*) as count FROM fact_conversations"
        ).fetchone()["count"]

        with_semantics = conn.execute("""
            SELECT COUNT(DISTINCT conversation_id) as count
            FROM fact_conversation_semantics
        """).fetchone()["count"]

        with_entities = conn.execute("""
            SELECT COUNT(DISTINCT conversation_id) as count
            FROM fact_conversation_entities
        """).fetchone()["count"]

        with_metrics = conn.execute("""
            SELECT COUNT(DISTINCT conversation_id) as count
            FROM fact_conversation_metrics
        """).fetchone()["count"]

        semantics_pct = (
            round((with_semantics / total_convs * 100), 1) if total_convs > 0 else 0
        )
        entities_pct = (
            round((with_entities / total_convs * 100), 1) if total_convs > 0 else 0
        )
        metrics_pct = (
            round((with_metrics / total_convs * 100), 1) if total_convs > 0 else 0
        )
        overall_pct = round((semantics_pct + entities_pct + metrics_pct) / 3, 1)

        return jsonify(
            {
                "total_conversations": total_convs,
                "semantics_completeness": semantics_pct,
                "entities_completeness": entities_pct,
                "metrics_completeness": metrics_pct,
                "overall_completeness": overall_pct,
            }
        )
    finally:
        conn.close()


@app.route("/api/admin/db-stats")
def get_db_stats():
    conn = get_db_connection()

    try:
        stats = {}

        tables = [
            "fact_conversations",
            "fact_conversation_entities",
            "fact_conversation_semantics",
            "dim_brands",
            "dim_crops",
            "dim_pests",
            "dim_user",
        ]

        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) as count FROM {table}").fetchone()
            stats[table] = count["count"]

        date_range = conn.execute("""
            SELECT
                MIN(date_recorded) as min_date,
                MAX(date_recorded) as max_date
            FROM fact_conversations
        """).fetchone()

        stats["date_range"] = {
            "min": date_range["min_date"],
            "max": date_range["max_date"],
        }

        return jsonify(stats)
    finally:
        conn.close()


@app.route("/api/debug/companies")
def debug_companies():
    """Debug endpoint to check company data"""
    conn = get_db_connection()
    try:
        # Get all companies
        companies = conn.execute("""
            SELECT company_code, company_name, COUNT(db.brand_code) as brand_count
            FROM dim_companies dc
            LEFT JOIN dim_brands db ON dc.company_code = db.company_code
            GROUP BY dc.company_code, dc.company_name
            ORDER BY brand_count DESC
        """).fetchall()

        # Get companies with sentiment data
        companies_with_data = conn.execute("""
            SELECT DISTINCT dc.company_code, dc.company_name, COUNT(DISTINCT fce.conversation_id) as mentions
            FROM dim_companies dc
            JOIN dim_brands db ON dc.company_code = db.company_code
            JOIN fact_conversation_entities fce ON db.brand_code = fce.entity_code
            WHERE fce.entity_type = 'brand'
            GROUP BY dc.company_code, dc.company_name
            ORDER BY mentions DESC
        """).fetchall()

        return jsonify(
            {
                "all_companies": [dict_from_row(c) for c in companies],
                "companies_with_data": [dict_from_row(c) for c in companies_with_data],
                "configured_competitors": COMPETITORS,
                "rallis_code": COROMANDEL_COMPANY_CODE,
            }
        )
    finally:
        conn.close()


################################################
# User management routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        success, role = auth.check_password(username, password)
        if success:
            session["logged_in"] = True
            session["username"] = username
            session["user_role"] = role
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid Credentials")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # Get role from form, default to customer_admin
        role = request.form.get("role", "customer_admin")
        # Only allow admin/customer_admin roles
        if role not in ["admin", "customer_admin"]:
            role = "customer_admin"
        if auth.add_user(username, password, role):
            return redirect(url_for("login"))
        else:
            return render_template("register.html", error="User already exists")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("username", None)
    return redirect(url_for("login"))


# ==================== MAIN ROUTE ====================


@app.route("/")
@login_required
def index():
    user_role = session.get("user_role", "customer_admin")
    return render_template("dashboard.html", user_role=user_role)


################################################

if __name__ == "__main__":
    # Initialize default users if they don't exist
    existing_users = auth.load_users()
    if "admin" not in existing_users:
        auth.add_user("admin", "adminpass", role="admin")
    if "customer" not in existing_users:
        auth.add_user("customer", "customer123", role="customer_admin")
    app.run(debug=True, host="0.0.0.0", port=5000)
