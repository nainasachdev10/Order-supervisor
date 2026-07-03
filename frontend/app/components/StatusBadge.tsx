const COLORS: Record<string, string> = {
  active: "bg-emerald-500/20 text-emerald-300",
  paused: "bg-amber-500/20 text-amber-300",
  closed: "bg-sky-500/20 text-sky-300",
  terminated: "bg-rose-500/20 text-rose-300",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${COLORS[status] || "bg-gray-500/20 text-gray-300"}`}>
      {status}
    </span>
  );
}
