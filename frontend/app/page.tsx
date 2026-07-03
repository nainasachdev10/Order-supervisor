"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Supervisor, Run } from "../lib/api";
import StatusBadge from "./components/StatusBadge";

export default function Dashboard() {
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [showSupForm, setShowSupForm] = useState(false);
  const [supName, setSupName] = useState("");
  const [supInstruction, setSupInstruction] = useState("");
  const [supWakeGuidance, setSupWakeGuidance] = useState("");

  const [orderId, setOrderId] = useState("");
  const [selectedSup, setSelectedSup] = useState("");

  const refresh = async () => {
    try {
      const [s, r] = await Promise.all([api.listSupervisors(), api.listRuns()]);
      setSupervisors(s);
      setRuns(r);
      if (!selectedSup && s.length) setSelectedSup(s[0].id);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  const createSupervisor = async () => {
    if (!supName || !supInstruction) return;
    await api.createSupervisor({
      name: supName,
      base_instruction: supInstruction,
      wake_up_guidance: supWakeGuidance,
    });
    setSupName("");
    setSupInstruction("");
    setSupWakeGuidance("");
    setShowSupForm(false);
    refresh();
  };

  const startRun = async () => {
    if (!orderId || !selectedSup) return;
    await api.createRun({ order_id: orderId, supervisor_id: selectedSup });
    setOrderId("");
    refresh();
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="card p-4 text-sm text-rose-300 border-rose-800">
          Couldn't reach the API at NEXT_PUBLIC_API_URL. Is the backend running? ({error})
        </div>
      )}

      <section className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Supervisor templates</h2>
          <button className="btn" onClick={() => setShowSupForm((v) => !v)}>
            {showSupForm ? "cancel" : "+ new template"}
          </button>
        </div>

        {showSupForm && (
          <div className="space-y-3 mb-4 border-t border-line pt-4">
            <input
              className="w-full bg-ink border border-line rounded-lg px-3 py-2 text-sm"
              placeholder="Template name (e.g. Standard Order Supervisor)"
              value={supName}
              onChange={(e) => setSupName(e.target.value)}
            />
            <textarea
              className="w-full bg-ink border border-line rounded-lg px-3 py-2 text-sm"
              placeholder="Base instruction..."
              rows={3}
              value={supInstruction}
              onChange={(e) => setSupInstruction(e.target.value)}
            />
            <input
              className="w-full bg-ink border border-line rounded-lg px-3 py-2 text-sm"
              placeholder="Wake-up guidance (optional, e.g. 'wake immediately on payment issues')"
              value={supWakeGuidance}
              onChange={(e) => setSupWakeGuidance(e.target.value)}
            />
            <button className="btn btn-accent" onClick={createSupervisor}>Create template</button>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {supervisors.map((s) => (
            <div key={s.id} className="border border-line rounded-lg p-3">
              <div className="font-medium text-sm">{s.name}</div>
              <div className="text-xs text-gray-400 mt-1 line-clamp-2">{s.base_instruction}</div>
              <div className="text-[11px] text-gray-500 mt-2 mono">tools: {s.tools.length}</div>
            </div>
          ))}
          {supervisors.length === 0 && (
            <div className="text-sm text-gray-500">
              No templates yet. Create one, or run <code className="mono">python -m seed</code> in the backend.
            </div>
          )}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="font-semibold mb-3">Start a run</h2>
        <div className="flex flex-wrap gap-3 items-center">
          <input
            className="bg-ink border border-line rounded-lg px-3 py-2 text-sm w-48"
            placeholder="Order ID (e.g. ORD-1001)"
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
          />
          <select
            className="bg-ink border border-line rounded-lg px-3 py-2 text-sm"
            value={selectedSup}
            onChange={(e) => setSelectedSup(e.target.value)}
          >
            {supervisors.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <button className="btn btn-accent" onClick={startRun} disabled={!orderId || !selectedSup}>
            Start supervision
          </button>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="font-semibold mb-3">Runs</h2>
        <div className="divide-y divide-line">
          {runs.map((r) => (
            <Link
              key={r.id}
              href={`/runs/${r.id}`}
              className="flex items-center justify-between py-3 hover:bg-ink/50 px-2 -mx-2 rounded-lg"
            >
              <div>
                <div className="text-sm font-medium">{r.order_id}</div>
                <div className="text-xs text-gray-500 mono">{r.workflow_id}</div>
              </div>
              <div className="flex items-center gap-3">
                {r.next_wake_time && (
                  <span className="text-xs text-gray-500">
                    wakes {new Date(r.next_wake_time).toLocaleTimeString()}
                  </span>
                )}
                <StatusBadge status={r.status} />
              </div>
            </Link>
          ))}
          {runs.length === 0 && <div className="text-sm text-gray-500 py-3">No runs yet.</div>}
        </div>
      </section>
    </div>
  );
}
