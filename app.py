import os
from flask import Flask, request, jsonify, Response
import io
from flask_cors import CORS
import json
from supabase import create_client
import pandas as pd 

from flask import Response


app = Flask(__name__)
CORS(app)

key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhobXJhYW9qcnhxZGhycWxmcnFtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQxMTgzMzMsImV4cCI6MjA4OTY5NDMzM30.bG9RX6_pICuGOk9bbigJHm-xybyZvZLxR7-lQYiIbZ0"
url = "https://xhmraaojrxqdhrqlfrqm.supabase.co"

supabase = create_client(url, key)

# @app.route('/analytics', methods=['POST'])
# def analytics():
#     try:
#         data = request.get_json()

#         if not data:
#             return jsonify({'error': 'No data'}), 400

#         if not isinstance(data, list):
#             data = [data]

#         with open('analytics.jsonl', 'a') as f:
#             for event in data:
#                 print(event)
#                 f.write(json.dumps(event) + '\n')

#         return jsonify({'status': 'ok'}), 200

#     except Exception as e:
#         print('Erro:', e)
#         return jsonify({'error': 'server error'}), 500

@app.route('/analytics', methods=['POST'])
def analytics():
    data = request.get_json()

    if not isinstance(data, list):
        data = [data]

    cleaned = []

    for e in data:
        cleaned.append({
            "event": e.get("event"),
            "level": e.get("level"),
            "attempt": e.get("attempt"),
            "time_in_level": e.get("time_in_level"),
            "session_id": e.get("session_id"),
            "timestamp": e.get("timestamp"),
            "death_cause": e.get("death_cause"),
            "client_id": e.get("client_id"),
            "data": e  # tudo extra vai aqui
        })

    supabase.table('events').insert(cleaned).execute()

    return jsonify({'status': 'ok'})


@app.route('/analytics/view', methods=['GET'])
def view_analytics():
    try:
        with open('analytics.jsonl', 'r') as f:
            lines = f.readlines()

        # retorna só os últimos 50 eventos
        last = lines[-50:]
        data = [json.loads(line) for line in last]

        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analytics/summary', methods=['GET'])
def analytics_summary():
    import json
    from collections import defaultdict

    levels = defaultdict(lambda: {
        "starts": 0,
        "fails": 0,
        "completes": 0,
        "attempts": []
    })

    death_causes = defaultdict(int)

    try:
        with open('analytics.jsonl', 'r') as f:
            for line in f:
                e = json.loads(line)

                level = e.get('level')
                event = e.get('event')

                if not level or not event:
                    continue

                if event == 'level_start':
                    levels[level]["starts"] += 1

                elif event == 'level_fail':
                    levels[level]["fails"] += 1
                    death_causes[e.get('death_cause', 'unknown')] += 1
                    levels[level]["attempts"].append(e.get('attempt', 1))

                elif event == 'level_complete':
                    levels[level]["completes"] += 1
                    levels[level]["attempts"].append(e.get('attempt', 1))

        # calcular médias
        for lvl in levels:
            attempts = levels[lvl]["attempts"]
            if attempts:
                levels[lvl]["avg_attempts"] = sum(attempts) / len(attempts)
            else:
                levels[lvl]["avg_attempts"] = 0

        return jsonify({
            "levels": levels,
            "death_causes": death_causes
        })

    except Exception as e:
        return jsonify({'error': str(e)})


from flask import render_template, request

@app.route('/analytics/dashboard', methods=['GET'])
def dashboard():
    supabase.rpc('refresh_analytics').execute()

    session_id = request.args.get('session_id')
    client_id = request.args.get('client_id')

    if session_id:
        response = supabase.table('analytics_by_session') \
            .select("*").eq('session_id', session_id).execute()
    elif client_id:
        response = supabase.table('analytics_by_client') \
            .select("*").eq('client_id', client_id).execute()
    else:
        response = supabase.table('analytics_summary').select("*").execute()

    responseSession = supabase.table('analytics_by_session').select("session_id").execute()
    responseClient = supabase.table('analytics_by_client').select("client_id").execute()

    sessions = list(set(row['session_id'] for row in responseSession.data))
    clients = list(set(row['client_id'] for row in responseClient.data))

    data = response.data[0]["data"]

    levels_raw = data.get("levels", {})
    death_causes = data.get("death_causes", {}) or {}
    portal_stats = data.get("portal", {})
    total_events = data.get("total_events", 0)
    total_sessions = data.get("sessions", 0)

    # normalizar níveis
    levels = []
    for lvl, d in levels_raw.items():
        start = d.get("starts", 0)
        complete = d.get("completes", 0)
        fail = d.get("fails", 0)

        cr = round((complete / start * 100), 1) if start else 0
        fr = round((fail / start * 100), 1) if start else 0

        levels.append({
            "lvl": lvl,
            "start": start,
            "complete": complete,
            "fail": fail,
            "avg_time": round(d.get("avg_time", 0), 1),
            "cr": cr,
            "fr": fr,
            "cr_color": "#4ade80" if cr >= 70 else "#facc15" if cr >= 40 else "#f87171",
            "fr_color": "#f87171" if fr >= 50 else "#facc15" if fr >= 25 else "#4ade80",
        })

    levels.sort(key=lambda x: int(x["lvl"]) if str(x["lvl"]).isdigit() else 999)

    # mortes
    total_deaths = sum(death_causes.values()) or 1
    death_list = []
    for cause, count in sorted(death_causes.items(), key=lambda x: -x[1]):
        pct = round(count / total_deaths * 100, 1)
        death_list.append({
            "cause": cause,
            "count": count,
            "pct": pct
        })

    portal_rate = round(
        portal_stats.get('buyed', 0) / portal_stats.get('moved', 1) * 100, 1
    ) if portal_stats.get('moved', 0) else 0

    return render_template(
        "dashboard.html",
        sessions=sessions,
        clients=clients,
        levels=levels,
        deaths=death_list,
        total_events=total_events,
        total_sessions=total_sessions,
        total_levels=len(levels),
        total_fails=sum(l["fail"] for l in levels),
        portal_stats=portal_stats,
        portal_rate=portal_rate
    )

@app.route('/analytics/export-events-xls', methods=['GET'])
def export_events_xls():

    all_rows = []
    page_size = 1000
    start = 0

    while True:
        response = supabase.table('events') \
            .select("*") \
            .range(start, start + page_size - 1) \
            .execute()

        batch = response.data

        if not batch:
            break

        all_rows.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    # 🔥 processa igual antes
    processed_rows = []

    for row in all_rows:
        base = row.copy()
        event_type = row.get("event")
        data = row.get("data") or {}

        base.pop("data", None)

        if isinstance(data, dict) and event_type in data:
            event_data = data[event_type]

            if isinstance(event_data, dict):
                from pandas import json_normalize

                flat = json_normalize(event_data, sep='_').to_dict(orient='records')[0]

                for key, value in flat.items():
                    base[f"{event_type}_{key}"] = value

        processed_rows.append(base)

    df = pd.DataFrame(processed_rows)

    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)

    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=events.xlsx"
        }
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)