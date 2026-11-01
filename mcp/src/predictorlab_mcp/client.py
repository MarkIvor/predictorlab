import httpx


class PredictorLabClient:
    def __init__(self, base_url: str, api_key: str, jwt: str | None = None, timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"}
        self.http = httpx.Client(base_url=self.base, headers=headers, timeout=timeout)
        self.jwt = jwt

    def _admin_headers(self):
        return {"Authorization": f"Bearer {self.jwt}"} if self.jwt else {}

    def list_models(self) -> list[dict]:
        return self.http.get("/api/v1/models").json()

    def get_schema(self, model_id: int) -> dict:
        return self.http.get(f"/api/v1/models/{model_id}/schema").json()

    def predict(self, model_id: int, data: list[dict], include: list[str] | None = None,
                version: int | None = None) -> dict:
        body: dict = {"data": data, "include": include or []}
        if version is not None:
            body["version"] = version
        return self.http.post(f"/api/v1/models/{model_id}/predict", json=body).json()

    def explain(self, model_id: int, data: dict) -> dict:
        return self.http.post(f"/api/v1/models/{model_id}/explain", json={"data": data}).json()

    def what_if(self, model_id: int, data: dict, changes: dict) -> dict:
        return self.http.post(f"/api/v1/models/{model_id}/whatif",
                             json={"data": data, "changes": changes}).json()

    def counterfactual(self, model_id: int, data: dict, direction: str = "below") -> dict:
        return self.http.post(f"/api/v1/models/{model_id}/counterfactual",
                             json={"data": data, "direction": direction}).json()

    def get_model_card(self, model_id: int) -> str:
        r = self.http.get(f"/api/v1/models/{model_id}/card")
        card = r.json()
        text = card.get("card_md") or ""
        if card.get("llm_narrative"):
            text = card["llm_narrative"] + "\n\n" + text
        return text

    def get_drift_status(self, model_id: int) -> dict:
        reports = self.http.get(f"/api/v1/models/{model_id}/monitor").json()
        if not reports:
            return {"status": "NO_REPORTS", "detail": "Отчётов дрейфа нет — запустите проверку на вкладке MONITOR"}
        latest = reports[0]
        return {
            "status": latest.get("status"),
            "window_days": latest.get("window_days"),
            "psi_prediction": latest.get("psi_prediction"),
            "top_psi": latest.get("top_psi"),
            "live_metrics": latest.get("live_metrics"),
            "created_at": latest.get("created_at"),
        }

    def train_model(self, model_id: int, mode: str = "quick") -> dict:
        r = self.http.post(f"/api/models/{model_id}/train", json={"mode": mode},
                           headers=self._admin_headers())
        return r.json()
