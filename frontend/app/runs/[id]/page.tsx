"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, RunDetail } from "../../../lib/api";
import StatusBadge from "../../components/StatusBadge";
import { EVENT_TYPES } from "../../constants";

function TimelineItem({ item }: { item: RunDetail["timeline"][number] }) {
  const time = new Date(item.created_at).toLocaleTimeString();
  const kindStyles: Record<string, string> = {
    event: "border-l-sky-500",
    agent_decision: "border-l-accent",
    tool_call: "border-l-warn",
    system: "border-l-gray-500",
  };

  return (
    <div className={`pl-3 border-l-2 ${kindStyles[item.type] || "border-l-gray-600"} py-2`}>
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="mono">{time}</span>
        <span className="uppercase tracking-wide">{item.type.replace("_", " ")}</span>
        {!item.important && <span className="text-gray-600">(minor)</span>}
      </div>
      {item.type === "event" && (
        <div className="text-sm mt-0.5">
          <span className="font-medium">{item.payload.event_type}</span>
          {Object.keys(item.payload.payload || {}).length > 0 && (
            <span className="text-gray-500 mono"> {JSON.stringify(item.payload.payload)}</span>
          )}
        </div>
      )}
      {item.type === "agent_decision" && (
        <div className="text-sm mt-0.5 text-gray-300">
          <span className="text-gray-500">[{item.payload.trigger}]</span> {item.payload.reasoning}
        </div>
      )}
      {item.type === "tool_call" && (
        <div className="text-sm mt-0.5">
          <span className="font-medium text-warn">{item.payload.tool}</span>
          <span className="text-gray-500 mono"> → {JSON.stringify(item.payload.result)}</span>
        </div>
      )}
      {item.type === "system" && (
        <div className="text-sm mt-0.5 text-gray-400">{JSON.stringify(item.payload)}</div>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eventType, setEventType] = useState(EVENT_TYPES[0]);
  const [instruction, setInstruction] = useState("");

  const refresh = async () => {
    try {
      const r = await api.getRun(runId);
      setRun(r);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [runId]);

  if (error) return <div className="card p-5 text-rose-300 text-sm">{error}</div>;
  if (!run) return <div className="text-sm text-gray-500">Loading...</div>;

  const isTerminal = run.status === "closed" || run.status === "terminated";

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold">{run.order_id}</h1>
              <div className="text-xs text-gray-500 mono">{run.workflow_id}</div>
            </div>
            <StatusBadge status={run.status} />
          </div>

          {!isTerminal && (
            <div className="flex gap-2 mt-4">
              {run.status === "active" ? (
                <button className="btn" onClick={() => api.interrupt(runId).then(refresh)}>pause</button>
              ) : (
                <button className="btn" onClick={() => api.resume(runId).then(refresh)}>resume</button>
              )}
              <button
                className="btn text-rose-300 border-rose-800"
                onClick={() => api.terminate(runId).then(refresh)}
              >
                terminate
              </button>
            </div>
          )}
        </div>

        <div className="card p-5">
          <h2 className="font-semibold mb-3">Timeline</h2>
          <div className="max-h-[520px] overflow-y-auto pr-1">
            {run.timeline.length === 0 && <div className="text-sm text-gray-500">Nothing yet.</div>}
            {run.timeline.map((item) => (
              <TimelineItem key={item.id} item={item} />
            ))}
          </div>
        </div>

        {run.final_summary && (
          <div className="card p-5 border-sky-800">
            <h2 className="font-semibold mb-3 text-sky-300">Final summary</h2>
            <p className="text-sm mb-3">{run.final_summary.summary}</p>
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-xs uppercase text-gray-500 mb-1">Key actions</div>
                <ul className="list-disc list-inside space-y-0.5">
                  {(run.final_summary.key_actions || []).map((a: string, i: number) => <li key={i}>{a}</li>)}
                </ul>
              </div>
              <div>
                <div className="text-xs uppercase text-gray-500 mb-1">Learnings</div>
                <ul className="list-disc list-inside space-y-0.5">
                  {(run.final_summary.learnings || []).map((a: string, i: number) => <li key={i}>{a}</li>)}
                </ul>
              </div>
              <div className="sm:col-span-2">
                <div className="text-xs uppercase text-gray-500 mb-1">Recommendations</div>
                <ul className="list-disc list-inside space-y-0.5">
                  {(run.final_summary.recommendations || []).map((a: string, i: number) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-6">
        <div className="card p-5">
          <h2 className="font-semibold mb-2">Memory summary</h2>
          <p className="text-sm text-gray-300">{run.memory_summary || "—"}</p>
          {run.next_wake_time && (
            <div className="text-xs text-gray-500 mt-3">
              Next scheduled wake-up: {new Date(run.next_wake_time).toLocaleString()}
            </div>
          )}
        </div>

        <div className="card p-5">
          <h2 className="font-semibold mb-2">Extra instructions</h2>
          <ul className="text-sm space-y-1 mb-3">
            {run.extra_instructions.map((ins, i) => <li key={i} className="text-gray-300">• {ins}</li>)}
            {run.extra_instructions.length === 0 && <li className="text-gray-500">None yet.</li>}
          </ul>
          {!isTerminal && (
            <div className="flex gap-2">
              <input
                className="flex-1 bg-ink border border-line rounded-lg px-2 py-1.5 text-sm"
                placeholder="e.g. escalate immediately if delayed"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              />
              <button
                className="btn btn-accent"
                onClick={() => { if (instruction) { api.addInstruction(runId, instruction).then(() => { setInstruction(""); refresh(); }); } }}
              >
                add
              </button>
            </div>
          )}
        </div>

        {!isTerminal && (
          <div className="card p-5">
            <h2 className="font-semibold mb-2">Inject event</h2>
            <div className="flex gap-2">
              <select
                className="flex-1 bg-ink border border-line rounded-lg px-2 py-1.5 text-sm"
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
              >
                {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <button
                className="btn btn-accent"
                onClick={() => api.sendEvent(runId, eventType).then(refresh)}
              >
                send
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
