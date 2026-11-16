from pathlib import Path
from datetime import datetime
import shutil

backend_path = Path("backend/app/routes/queue.py")
frontend_path = Path("frontend/src/App.jsx")

backend = backend_path.read_text()
frontend = frontend_path.read_text()

def replace_once(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
             f"{label}: expected 1 match, found {count}. "
            "No application files have been written."
        )
    return source.replace(old, new, 1)

# BACKEND: add date selection only to the Admin queue retrieval endpoint.
backend = replace_once(
    backend,
    '''    today = queue_date_today()

    try:
        rows = db.session.execute(
            text("""
                SELECT
                    qt.id::text AS id,''',
    '''    today = queue_date_today()
    requested_date = request.args.get("date")

    if requested_date:
        try:
            selected_date = datetime.strptime(
                requested_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            return jsonify({
                "status": "error",
                "message": "Invalid queue date. Use YYYY-MM-DD.",
            }), 400
    else:
        selected_date = today

    try:
        rows = db.session.execute(
            text("""
                SELECT
                    qt.id::text AS id,''',
    "Backend queue date selection"
)

backend = replace_once(
    backend,
    '''            {"business_id": business_id, "queue_date": today},
        ).mappings().all()''',
    '''            {"business_id": business_id, "queue_date": selected_date},
        ).mappings().all()''',
    "Admin queue retrieval date filter"
)

backend = replace_once(
    backend,
    '''            "queue_date": today.isoformat(),''',
    '''            "queue_date": selected_date.isoformat(),''',
    "Admin queue response date"
)

# FRONTEND: date state.
frontend = replace_once(
    frontend,
    '''  const [queue, setQueue] = useState([]);
  const [queuePaused, setQueuePaused] = useState(false);''',
    '''  const [queue, setQueue] = useState([]);
  const [queueDate, setQueueDate] = useState(
    () => new Date().toLocaleDateString("en-CA")
  );
  const [queuePaused, setQueuePaused] = useState(false);''',
    "Queue date state"
)

# Frontend API request.
frontend = replace_once(
    frontend,
    '''        api(`/businesses/${businessId}/queue`, {}, authToken),''',
    '''        api(
          `/businesses/${businessId}/queue?date=${encodeURIComponent(queueDate)}`,
          {},
          authToken
        ),''',
    "Queue retrieval API request"
)

# Queue loader effect dependency.
frontend = replace_once(
    frontend,
    '''  }, [selectedBusinessId, token]);

  useEffect(() => {
    if (!selectedBusinessId || !token) return undefined;
    const timer = window.setInterval(''',
    '''  }, [selectedBusinessId, token, queueDate]);

  useEffect(() => {
    if (!selectedBusinessId || !token) return undefined;
    const timer = window.setInterval(''',
    "Queue loader dependency"
)

# Polling effect dependency.
frontend = replace_once(
    frontend,
    '''  }, [selectedBusinessId, token]);

  const loadQueue = async () => {''',
    '''  }, [selectedBusinessId, token, queueDate]);

  const loadQueue = async () => {''',
    "Queue polling dependency"
)

# Prevent modifying historical records.
frontend = replace_once(
    frontend,
    '''  const performQueueAction = async (actionKey, requestPath, successMessage) => {
    if (!selectedBusinessId || queueMutationInFlight.current) return;''',
    '''  const performQueueAction = async (actionKey, requestPath, successMessage) => {
    if (!selectedBusinessId || queueMutationInFlight.current) return;

    if (queueDate !== new Date().toLocaleDateString("en-CA")) {
      notify("Historical queue records are read-only. Select today's date to manage the live queue.");
      return;
    }''',
    "Historical queue action protection"
)

# Queue heading and date selector.
frontend = replace_once(
    frontend,
    '''                <div className="panel-heading">
                  <div>
                    <h2>Live waiting list</h2>
                    <p>
                      {selectedBusiness?.business_name ||
                        "Select a business to view its queue"}
                    </p>
                  </div>

                  <span''',
    '''                <div className="panel-heading">
                  <div>
                    <h2>
                      {queueDate === new Date().toLocaleDateString("en-CA")
                        ? "Live waiting list"
                        : "Queue history"}
                    </h2>
                    <p>
                      {selectedBusiness?.business_name ||
                        "Select a business to view its queue"}
                    </p>
                    <label htmlFor="queueDateFilter">
                      View queue date
                      <input
                        id="queueDateFilter"
                        type="date"
                        className="input"
                        value={queueDate}
                        max={new Date().toLocaleDateString("en-CA")}
                        onChange={(event) =>
                          setQueueDate(
                            event.target.value ||
                            new Date().toLocaleDateString("en-CA")
                          )
                        }
                      />
                    </label>
                    {queueDate !== new Date().toLocaleDateString("en-CA") && (
                      <small>Historical records are read-only.</small>
                    )}
                  </div>

                  <span''',
    "Queue history selector"
)

frontend = replace_once(
    frontend,
    '''                detail="Today's queue records"''',
    '''                detail={
                  queueDate === new Date().toLocaleDateString("en-CA")
                    ? "Today's queue records"
                    : `Records for ${queueDate}`
                }''',
    "Queue statistic date"
)

frontend = replace_once(
    frontend,
    '''                detail="Completed today"''',
    '''                detail={
                  queueDate === new Date().toLocaleDateString("en-CA")
                    ? "Completed today"
                    : `Completed on ${queueDate}`
                }''',
    "Completed statistic date"
)

# Save only after every expected section has matched.
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

shutil.copy2(
    backend_path,
    Path(f"{backend_path}.backup_{stamp}")
)
shutil.copy2(
    frontend_path,
    Path(f"{frontend_path}.backup_{stamp}")
)

backend_path.write_text(backend)
frontend_path.write_text(frontend)

print("SUCCESS: Queue history changes applied.")
print("Backup suffix:", stamp)
print("Updated backend:", backend_path)
print("Updated frontend:", frontend_path)
