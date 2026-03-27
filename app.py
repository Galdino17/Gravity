import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
from supabase import create_client

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
    
@app.route('/analytics/dashboard', methods=['GET'])
def dashboard():
    supabase.rpc('refresh_analytics').execute()
    session_id = request.args.get('session_id')
    client_id = request.args.get('client_id')

    if session_id:
        response = supabase.table('analytics_by_session').select("*").eq('session_id', session_id).execute()

    elif client_id:
        response = supabase.table('analytics_by_client').select("*").eq('client_id', client_id).execute()

    else:
        response = supabase.table('analytics_summary').select("*").execute()

    responseSession = supabase.table('analytics_by_session') \
    .select("session_id") \
    .execute()

    responseClient = supabase.table('analytics_by_client') \
        .select("client_id") \
        .execute()

    sessions = list(set(row['session_id'] for row in responseSession.data))
    clients = list(set(row['client_id'] for row in responseClient.data))

    session_options = "".join(
    f'<option value="{s}">{s}</option>' for s in sessions
    ).join('<select name="session_id" onchange="this.form.submit()">')

    client_options = "".join(
        f'<option value="{c}">{c}</option>' for c in clients
    ).join('<select name="client_id" onchange="this.form.submit()">')

    data = response.data[0]["data"]

    levels_raw = data.get("levels", {})
    death_causes = data.get("death_causes", {})
    portal_stats = data.get("portal", {})
    total_events = data.get("total_events", 0)
    total_sessions = data.get("sessions", 0)

    # normalizar
    levels = {}
    for lvl, d in levels_raw.items():
        levels[lvl] = {
            "start": d.get("starts", 0),
            "fail": d.get("fails", 0),
            "complete": d.get("completes", 0),
            "avg_time": round(d.get("avg_time", 0), 1)
        }

    sorted_levels = sorted(levels.items(), key=lambda x: (
        int(x[0]) if str(x[0]).isdigit() else float('inf')
    ))
    def completion_rate(data):
        return round((data['complete'] / data['start'] * 100), 1) if data['start'] > 0 else 0

    def fail_rate(data):
        return round((data['fail'] / data['start'] * 100), 1) if data['start'] > 0 else 0

    rows_html = ""
    for lvl, data in sorted_levels:
        cr = completion_rate(data)
        fr = fail_rate(data)
        cr_color = "#4ade80" if cr >= 70 else "#facc15" if cr >= 40 else "#f87171"
        fr_color = "#f87171" if fr >= 50 else "#facc15" if fr >= 25 else "#4ade80"
        rows_html += f"""
        <tr>
            <td class="level-cell">
                <span class="level-badge">LVL {lvl}</span>
            </td>
            <td>{data['start']:,}</td>
            <td>{data['complete']:,}</td>
            <td>{data['fail']:,}</td>
            <td>
                <div class="rate-cell">
                    <span class="rate-dot" style="background:{cr_color}"></span>
                    {cr}%
                    <div class="bar-wrap">
                        <div class="bar" style="width:{cr}%;background:{cr_color}"></div>
                    </div>
                </div>
            </td>
            <td>
                <div class="rate-cell">
                    <span class="rate-dot" style="background:{fr_color}"></span>
                    {fr}%
                    <div class="bar-wrap">
                        <div class="bar" style="width:{min(fr,100)}%;background:{fr_color}"></div>
                    </div>
                </div>
            </td>
            <td class="time-cell">{data['avg_time']}s</td>
        </tr>
        """

    death_rows_html = ""
    if death_causes is not None:
        print(death_causes)
        total_deaths = sum(death_causes.values()) or 1
        sorted_deaths = sorted(death_causes.items(), key=lambda x: -x[1])
    else:
        total_deaths = 0
        sorted_deaths= []

    for cause, count in sorted_deaths:
        pct = round(count / total_deaths * 100, 1)
        death_rows_html += f"""
        <tr>
            <td class="cause-cell">
                <span class="skull">☠</span> {cause}
            </td>
            <td>{count:,}</td>
            <td>
                <div class="bar-wrap wide">
                    <div class="bar" style="width:{pct}%;background:#f87171"></div>
                </div>
                {pct}%
            </td>
        </tr>
        """

    portal_rate = (
        round(portal_stats['buyed'] / portal_stats['moved'] * 100, 1)
        if portal_stats['moved'] > 0 else 0
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Analytics Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0a0f;
    --surface: #111118;
    --border: #1e1e2e;
    --accent: #7c6af7;
    --accent-dim: #3d3580;
    --text: #e2e2f0;
    --muted: #6b6b8a;
    --green: #4ade80;
    --red: #f87171;
    --yellow: #facc15;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Outfit', sans-serif;
    min-height: 100vh;
    padding: 2rem;
  }}

  header {{
    display: flex;
    align-items: baseline;
    gap: 1rem;
    margin-bottom: 2.5rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 1.5rem;
  }}

  header h1 {{
    font-family: 'Space Mono', monospace;
    font-size: 1.4rem;
    letter-spacing: -0.03em;
    color: #fff;
  }}

  header .tag {{
    font-size: 0.7rem;
    background: var(--accent-dim);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 4px;
    font-family: 'Space Mono', monospace;
    letter-spacing: 0.05em;
  }}

  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin-bottom: 2.5rem;
  }}

  .kpi {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    transition: border-color 0.2s;
  }}

  .kpi:hover {{ border-color: var(--accent-dim); }}

  .kpi .label {{
    font-size: 0.72rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.5rem;
    font-family: 'Space Mono', monospace;
  }}

  .kpi .value {{
    font-size: 1.9rem;
    font-weight: 800;
    color: #fff;
    line-height: 1;
  }}

  .kpi .sub {{
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: 0.3rem;
  }}

  .section {{
    margin-bottom: 2.5rem;
  }}

  .section-title {{
    font-family: 'Space Mono', monospace;
    font-size: 0.75rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}

  .section-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }}

  .table-wrap {{
    overflow-x: auto;
    border-radius: 10px;
    border: 1px solid var(--border);
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
  }}

  thead tr {{
    background: #0f0f1a;
  }}

  thead th {{
    padding: 0.85rem 1.25rem;
    text-align: left;
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 400;
    white-space: nowrap;
  }}

  tbody tr {{
    border-top: 1px solid var(--border);
    transition: background 0.15s;
  }}

  tbody tr:hover {{
    background: #13131f;
  }}

  tbody td {{
    padding: 0.85rem 1.25rem;
    color: var(--text);
    white-space: nowrap;
    font-weight: 300;
  }}

  .level-cell {{ font-weight: 600; }}

  .level-badge {{
    background: var(--accent-dim);
    color: var(--accent);
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem;
    padding: 3px 8px;
    border-radius: 5px;
    letter-spacing: 0.05em;
  }}

  .rate-cell {{
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 120px;
  }}

  .rate-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }}

  .bar-wrap {{
    flex: 1;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    min-width: 50px;
  }}

  .bar-wrap.wide {{ min-width: 100px; }}

  .bar {{
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }}

  .time-cell {{
    font-family: 'Space Mono', monospace;
    font-size: 0.82rem;
    color: var(--accent);
  }}

  .cause-cell {{
    font-weight: 400;
    color: var(--muted);
  }}

  .skull {{
    margin-right: 4px;
    opacity: 0.6;
  }}

  .portal-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
  }}

  @media (max-width: 600px) {{
    body {{ padding: 1rem; }}
    .portal-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<header>
  <h1>&#9655; analytics</h1>
  <span class="tag">LIVE</span>

  <select name="session_id">
  <option value="">Todas sessões</option>
  {session_options}
</select>

<select name="client_id">
  <option value="">Todos clientes</option>
  {client_options}
</select>
</header>

<div class="kpi-grid">
  <div class="kpi">
    <div class="label">Total Eventos</div>
    <div class="value">{total_events:,}</div>
    <div class="sub">últimos 1000 carregados</div>
  </div>
  <div class="kpi">
    <div class="label">Sessões únicas</div>
    <div class="value" style="color:var(--yellow)">{total_sessions:,}</div>
    <div class="sub">session_ids distintos</div>
  </div>
  <div class="kpi">
    <div class="label">Níveis rastreados</div>
    <div class="value">{len(levels)}</div>
  </div>
  <div class="kpi">
    <div class="label">Total mortes</div>
    <div class="value" style="color:var(--red)">{sum(d['fail'] for d in levels.values()):,}</div>
  </div>
  <div class="kpi">
    <div class="label">Portais usados</div>
    <div class="value" style="color:var(--accent)">{portal_stats['moved']:,}</div>
  </div>
  <div class="kpi">
    <div class="label">Portais comprados</div>
    <div class="value" style="color:var(--green)">{portal_stats['buyed']:,}</div>
    <div class="sub">taxa de compra: {portal_rate}%</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Desempenho por nível</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Nível</th>
          <th>Starts</th>
          <th>Completes</th>
          <th>Fails</th>
          <th>Taxa conclusão</th>
          <th>Taxa falha</th>
          <th>Tempo médio</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">Causas de morte</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Causa</th>
          <th>Ocorrências</th>
          <th>Distribuição</th>
        </tr>
      </thead>
      <tbody>
        {death_rows_html if death_rows_html else '<tr><td colspan="3" style="color:var(--muted);padding:1.5rem">Nenhuma morte registrada.</td></tr>'}
      </tbody>
    </table>
  </div>
</div>

</body>
</html>"""

    from flask import Response
    return Response(html, mimetype='text/html')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)