"""
ApexMarket: In-Memory Database Store & Session Factory
Enables zero-setup local demonstration without external PostgreSQL or Redis dependencies.
"""
from datetime import datetime, timezone
import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy import text


class MockRow:
    def __init__(self, d: dict):
        self._d = d
        for k, v in d.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        if isinstance(idx, int):
            return list(self._d.values())[idx]
        return self._d[idx]

    def __getattr__(self, name):
        if name in self._d:
            return self._d[name]
        raise AttributeError(f"MockRow has no attribute {name}")

    def __contains__(self, item):
        return item in self._d


class MockMapping:
    def __init__(self, d: dict):
        self._d = d

    def __getitem__(self, key):
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()

    def items(self):
        return self._d.items()


class MockMappingsResult:
    def __init__(self, rows: list):
        self._rows = [r if isinstance(r, dict) else (r._d if isinstance(r, MockRow) else dict(r)) for r in rows]

    def first(self):
        return MockMapping(self._rows[0]) if self._rows else None

    def one(self):
        if not self._rows:
            raise ValueError("No rows returned")
        return MockMapping(self._rows[0])

    def all(self):
        return [MockMapping(r) for r in self._rows]

    def __iter__(self):
        return iter(MockMapping(r) for r in self._rows)


class MockResult:
    def __init__(self, rows: list):
        self._rows = [MockRow(r) if isinstance(r, dict) else r for r in rows]
        self._idx = 0

    def fetchone(self):
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None

    def fetchall(self):
        return self._rows

    def scalar(self):
        row = self.fetchone()
        if row is None:
            return None
        if isinstance(row, MockRow):
            return list(row._d.values())[0]
        if isinstance(row, (tuple, list)):
            return row[0]
        return row

    def scalar_one(self):
        row = self.fetchone()
        if row is None:
            raise ValueError("No rows returned from query")
        if isinstance(row, MockRow):
            return list(row._d.values())[0]
        if isinstance(row, (tuple, list)):
            return row[0]
        return row

    def one(self):
        row = self.fetchone()
        if row is None:
            raise ValueError("No rows returned")
        return row

    def scalars(self):
        class ScalarResult:
            def __init__(self, rows):
                self._rows = rows
            def all(self):
                res = []
                for r in self._rows:
                    if isinstance(r, MockRow):
                        res.append(list(r._d.values())[0])
                    elif isinstance(r, dict):
                        res.append(list(r.values())[0])
                    else:
                        res.append(r)
                return res
        return ScalarResult(self._rows)

    def mappings(self):
        return MockMappingsResult(self._rows)


class InMemoryTestStore:
    def __init__(self, seed_defaults: bool = True):
        self.clients = {}
        self.compute_nodes = {}
        self.batch_jobs = {}
        self.job_shreds = {}
        self.ledger_entries = {}
        self.payout_batches = {}
        self.payout_items = {}

        if seed_defaults:
            from app.api.routes_nodes import DEFAULT_SEEDED_NODES
            for n in DEFAULT_SEEDED_NODES:
                self.compute_nodes[n["node_id"]] = {
                    **n,
                    "trust_tier": n["trust_tier"] if isinstance(n["trust_tier"], str) else n["trust_tier"].value,
                    "pending_probation_micros": 0,
                    "withdrawable_micros": 240000,
                    "payout_pending_micros": 0,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                }

            # Seed a default client with $100.00
            import hashlib
            default_key = "default_apex_test_key"
            key_hash = hashlib.sha256(default_key.encode("utf-8")).hexdigest()
            client_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
            self.clients[client_id] = {
                "client_id": client_id,
                "organization_name": "Default Enterprise Client",
                "api_key_hash": key_hash,
                "available_balance_micros": 100_000_000,
                "locked_escrow_micros": 0,
                "hourly_spend_limit_micros": 50_000_000,
                "created_at": datetime.now(timezone.utc),
            }

    def execute_sql(self, sql_str: str, params: dict) -> MockResult:
        s = " ".join(sql_str.strip().split())

        # 0. Advisory locks
        if "pg_advisory_xact_lock" in s:
            return MockResult([])

        # 1. compute_nodes queries & count
        if "SELECT COUNT(*) FROM compute_nodes" in s or "SELECT count(*) FROM compute_nodes" in s.lower():
            return MockResult([{"count": len(self.compute_nodes)}])

        if s.startswith("SELECT * FROM compute_nodes"):
            if "WHERE node_id = :node_id" in s:
                nid = params.get("node_id")
                n = self.compute_nodes.get(nid)
                return MockResult([n] if n else [])
            return MockResult(list(self.compute_nodes.values()))

        if "SELECT node_id, withdrawable_micros, paypal_receiver_email FROM compute_nodes" in s:
            payable = [
                n for n in self.compute_nodes.values()
                if n.get("is_active", True) and n.get("withdrawable_micros", 0) >= 10000
            ]
            return MockResult(payable)

        if s.startswith("INSERT INTO compute_nodes"):
            nid = params["node_id"]
            self.compute_nodes[nid] = {
                "node_id": nid,
                "provider_name": params.get("provider_name", "Test Provider"),
                "endpoint_url": params.get("endpoint_url", "http://test/v1"),
                "model_id": params.get("model_id", "nvidia/nemotron-3-nano-30b-a3b"),
                "trust_tier": params.get("trust_tier", "PROBATION_SPOT"),
                "paypal_receiver_email": params.get("paypal_receiver_email", "node@example.com"),
                "input_price_per_1m_micros": params.get("input_price_per_1m_micros", params.get("input_price", 40000)),
                "output_price_per_1m_micros": params.get("output_price_per_1m_micros", params.get("output_price", 160000)),
                "max_concurrent_requests": params.get("max_concurrent_requests", params.get("max_concurrent", 10)),
                "pending_probation_micros": 0,
                "withdrawable_micros": 0,
                "payout_pending_micros": 0,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        # 2. clients lookup
        if "SELECT client_id FROM clients WHERE api_key_hash" in s:
            h = params.get("hash")
            for cid, c in self.clients.items():
                if c.get("api_key_hash") == h:
                    return MockResult([{"client_id": cid}])
            # Auto-provision if not found
            cid = uuid.uuid4()
            self.clients[cid] = {
                "client_id": cid,
                "organization_name": "Default Enterprise Client",
                "api_key_hash": h,
                "available_balance_micros": 100_000_000,
                "locked_escrow_micros": 0,
                "hourly_spend_limit_micros": 50_000_000,
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([{"client_id": cid}])

        if s.startswith("INSERT INTO clients"):
            cid = params["client_id"]
            self.clients[cid] = {
                "client_id": cid,
                "organization_name": params.get("organization_name", "Default Enterprise Client"),
                "api_key_hash": params.get("hash", params.get("key_hash")),
                "available_balance_micros": params.get("available", 100_000_000),
                "locked_escrow_micros": 0,
                "hourly_spend_limit_micros": params.get("hourly_limit", 50_000_000),
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        # 3. select client for update
        if "SELECT available_balance_micros, hourly_spend_limit_micros FROM clients" in s:
            cid = params["client_id"]
            c = self.clients.get(cid)
            if not c:
                c = {
                    "client_id": cid,
                    "organization_name": "Default Enterprise Client",
                    "available_balance_micros": 100_000_000,
                    "locked_escrow_micros": 0,
                    "hourly_spend_limit_micros": 50_000_000,
                }
                self.clients[cid] = c
            return MockResult([c])

        # 4. idempotency check in ledger
        if "SELECT 1 FROM ledger_entries WHERE idempotency_key" in s:
            k = params["key"]
            if k in self.ledger_entries:
                return MockResult([{"found": 1}])
            return MockResult([])

        # 5. hourly spend circuit breaker
        if "SELECT COALESCE(SUM(amount_micros), 0) FROM ledger_entries" in s:
            total = sum(
                e["amount_micros"] for e in self.ledger_entries.values()
                if e.get("credit_account") == params.get("escrow_account")
                and e.get("idempotency_key", "").startswith("escrow_lock:")
            )
            return MockResult([{"sum": total}])

        # 6. client balance updates
        if s.startswith("UPDATE clients"):
            cid = params.get("client_id")
            if cid and cid in self.clients:
                c = self.clients[cid]
                if "available_balance_micros - :amount" in s:
                    amt = params["amount"]
                    c["available_balance_micros"] -= amt
                    c["locked_escrow_micros"] += amt
                elif "locked_escrow_micros - :amount" in s:
                    amt = params["amount"]
                    c["locked_escrow_micros"] -= amt
                elif "locked_escrow_micros - :fee" in s:
                    fee = params["fee"]
                    c["locked_escrow_micros"] -= fee
                elif "locked_escrow_micros - :unused" in s:
                    unused = params["unused"]
                    c["locked_escrow_micros"] -= unused
                    c["available_balance_micros"] += unused
            return MockResult([])

        # 7. insert ledger entries
        if s.startswith("INSERT INTO ledger_entries"):
            k = params["key"]
            if k in self.ledger_entries:
                return MockResult([])
            eid = params.get("entry_id", uuid.uuid4())
            self.ledger_entries[k] = {
                "entry_id": eid,
                "idempotency_key": k,
                "job_id": params.get("job_id"),
                "shred_id": params.get("shred_id"),
                "debit_account": params.get("debit_account"),
                "credit_account": params.get("credit_account"),
                "amount_micros": params.get("amount_micros"),
                "description": params.get("description"),
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([{"entry_id": eid}])

        if "SELECT entry_id FROM ledger_entries WHERE idempotency_key" in s:
            k = params["key"]
            e = self.ledger_entries.get(k)
            return MockResult([{"entry_id": e["entry_id"]}] if e else [])

        # 8. query candidate compute nodes
        if "SELECT node_id, provider_name, endpoint_url, model_id, trust_tier" in s:
            from app.services.chaos_service import is_node_quarantined
            active = [
                n for n in self.compute_nodes.values()
                if n.get("is_active", True)
                and not is_node_quarantined(n.get("node_id", ""))
                and n.get("trust_tier") != "SLASHED"
            ]
            return MockResult(active)

        # 9. batch_jobs queries and inserts
        if s.startswith("INSERT INTO batch_jobs"):
            jid = params["job_id"]
            self.batch_jobs[jid] = {
                "job_id": jid,
                "client_id": params["client_id"],
                "sensitivity": params["sensitivity"],
                "status": "QUEUED",
                "total_prompts": params["total_prompts"],
                "max_tokens_per_prompt": params["max_tokens"],
                "max_cost_ceiling_micros": params["ceiling"],
                "reserved_escrow_micros": params["escrow"],
                "actual_settled_cost_micros": 0,
                "platform_fee_micros": 0,
                "baseline_anchor_cost_micros": params["baseline"],
                "baseline_batch_api_cost_micros": int(params["ceiling"] * 0.75),
                "total_makespan_ms": None,
                "created_at": params.get("created_at", datetime.now(timezone.utc)),
                "completed_at": None,
                "results_payload": None,
            }
            return MockResult([])

        if s.startswith("SELECT reserved_escrow_micros, baseline_anchor_cost_micros FROM batch_jobs"):
            jid = params["job_id"]
            job = self.batch_jobs.get(jid)
            return MockResult([job] if job else [])

        if "FROM batch_jobs WHERE job_id = :job_id" in s or "FROM batch_jobs WHERE job_id = :id" in s:
            jid = params.get("job_id") or params.get("id")
            job = self.batch_jobs.get(jid)
            return MockResult([job] if job else [])

        if s.startswith("UPDATE batch_jobs"):
            jid = params.get("job_id") or params.get("id")
            job = self.batch_jobs.get(jid)
            if job:
                if "status" in params:
                    job["status"] = params["status"]
                if "cost" in params:
                    job["actual_settled_cost_micros"] = params["cost"]
                if "fee" in params:
                    job["platform_fee_micros"] = params["fee"]
                if "makespan" in params:
                    job["total_makespan_ms"] = params["makespan"]
                if "completed_at" in params or "now" in params:
                    job["completed_at"] = params.get("completed_at", params.get("now"))
                if "results_payload" in params:
                    job["results_payload"] = params["results_payload"]
            return MockResult([])

        # 10. job_shreds queries and updates
        if s.startswith("INSERT INTO job_shreds"):
            sid = params["shred_id"]
            self.job_shreds[sid] = {
                "shred_id": sid,
                "job_id": params["job_id"],
                "node_id": params["node_id"],
                "status": "PENDING",
                "prompt_indices": params["indices"],
                "shred_cost_micros": params["cost"],
                "measured_input_tokens": 0,
                "measured_output_tokens": 0,
                "canary_pass_rate": None,
                "server_hmac_attestation": None,
                "retry_count": 0,
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        if "FROM job_shreds WHERE job_id = :job_id" in s or "FROM job_shreds WHERE job_id = :id" in s:
            jid = params.get("job_id") or params.get("id")
            shreds = [sh for sh in self.job_shreds.values() if sh["job_id"] == jid]
            return MockResult(shreds)

        if s.startswith("UPDATE job_shreds"):
            sid = params["shred_id"]
            shred = self.job_shreds.get(sid)
            if shred:
                if "status" in params:
                    shred["status"] = params["status"]
                elif "VERIFIED_PASS" in s:
                    shred["status"] = "VERIFIED_PASS"
                elif "VERIFIED_FAIL_REROUTED" in s:
                    shred["status"] = "VERIFIED_FAIL_REROUTED"
                elif "RUNNING" in s:
                    shred["status"] = "RUNNING"
                if "in_tok" in params:
                    shred["measured_input_tokens"] = params["in_tok"]
                if "out_tok" in params:
                    shred["measured_output_tokens"] = params["out_tok"]
                if "cost" in params:
                    shred["shred_cost_micros"] = params["cost"]
                if "pass_rate" in params:
                    shred["canary_pass_rate"] = params["pass_rate"]
                if "att" in params:
                    shred["server_hmac_attestation"] = params["att"]
                if "retry_count + 1" in s:
                    shred["retry_count"] += 1
            return MockResult([])

        # 11. compute_nodes credits & settlement
        if s.startswith("UPDATE compute_nodes"):
            if ":node" in params or ":node_id" in params:
                nid = params.get("node") or params.get("node_id")
                node = self.compute_nodes.get(nid)
                if node:
                    if "withdrawable_micros = withdrawable_micros - :amount" in s:
                        amt = params["amount"]
                        node["withdrawable_micros"] = max(0, node.get("withdrawable_micros", 0) - amt)
                        node["payout_pending_micros"] = node.get("payout_pending_micros", 0) + amt
                    elif "withdrawable_micros" in s and "amount" in params:
                        amt = params["amount"]
                        node["withdrawable_micros"] = node.get("withdrawable_micros", 0) + amt
                    elif "pending_probation_micros" in s and "amount" in params:
                        amt = params["amount"]
                        node["pending_probation_micros"] = node.get("pending_probation_micros", 0) + amt
                    if "trust_tier = 'SLASHED'" in s or "trust_tier = :trust_tier" in s:
                        node["trust_tier"] = params.get("trust_tier", "SLASHED")
                    if "is_active = FALSE" in s:
                        node["is_active"] = False
            elif "payout_pending_micros = 0" in s:
                for n in self.compute_nodes.values():
                    n["payout_pending_micros"] = 0
            return MockResult([])

        # 12. Payout batches & items
        if s.startswith("INSERT INTO payout_batches"):
            bid = params["id"]
            self.payout_batches[bid] = {
                "batch_id": bid,
                "total_amount_micros": params["total"],
                "status": "CREATED",
                "paypal_batch_id": None,
                "created_at": datetime.now(timezone.utc),
            }
            return MockResult([])

        if "FROM payout_batches WHERE batch_id = :id" in s:
            bid = params["id"]
            batch = self.payout_batches.get(bid)
            return MockResult([batch] if batch else [])

        if s.startswith("UPDATE payout_batches"):
            bid = params["id"]
            batch = self.payout_batches.get(bid)
            if batch:
                if "paypal" in params:
                    batch["paypal_batch_id"] = params["paypal"]
                if "status" in params:
                    batch["status"] = params["status"]
            return MockResult([])

        if s.startswith("INSERT INTO payout_items"):
            iid = params["item"]
            self.payout_items[iid] = {
                "item_id": iid,
                "batch_id": params["batch"],
                "node_id": params["node"],
                "amount_paid_micros": params["amount"],
                "remainder_carried_micros": params["remainder"],
                "payout_receiver_email": params["receiver"],
                "item_status": "PENDING",
            }
            return MockResult([])

        return MockResult([])


class MockAsyncSession:
    def __init__(self, store: InMemoryTestStore):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, statement, params=None):
        return self.store.execute_sql(str(statement), params or {})

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


class MockAsyncSessionFactory:
    def __init__(self, store: InMemoryTestStore):
        self.store = store

    def __call__(self):
        return MockAsyncSession(self.store)


global_in_memory_store = InMemoryTestStore(seed_defaults=True)
global_session_factory = MockAsyncSessionFactory(global_in_memory_store)


def get_in_memory_session() -> MockAsyncSession:
    return MockAsyncSession(global_in_memory_store)
