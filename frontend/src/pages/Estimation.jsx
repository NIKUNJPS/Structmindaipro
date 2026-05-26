import { useCallback, useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
    Calculator,
    CheckCircle2,
    CloudUpload,
    Download,
    FileIcon,
    History,
    Sparkles,
    Trash2,
} from "lucide-react";
import { motion } from "framer-motion";
import { api, errMessage } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { usePermissions } from "@/hooks/usePermissions";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { tokenStore } from "@/lib/auth";

export default function Estimation() {
    const { user } = useAuth();
    const { perms, isSuperAdmin, can } = usePermissions();
    const [role, setRole] = useState(
        user?.role === "super_admin" ? "detailer" : user?.role || "detailer",
    );
    const [schema, setSchema] = useState(null);
    const [rateLow, setRateLow] = useState(0);
    const [rateHigh, setRateHigh] = useState(0);
    const [files, setFiles] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [history, setHistory] = useState([]);

    useEffect(() => {
        if (!role) return;
        (async () => {
            try {
                const { data } = await api.get(`/api/estimation/schema/${role}`);
                setSchema(data.schema);
                setRateLow(data.schema.default_low);
                setRateHigh(data.schema.default_high);
            } catch (e) {
                toast.error(errMessage(e));
                setSchema(null);
            }
        })();
        // Clear AI result + files when switching roles (rates are role-specific)
        setResult(null);
        setFiles([]);
    }, [role]);

    const loadHistory = async () => {
        try {
            const { data } = await api.get("/api/estimation/");
            setHistory(data.items || []);
        } catch {}
    };

    useEffect(() => {
        loadHistory();
    }, []);

    const cannotRun = !isSuperAdmin && !can("canRunEstimation");

    const onDrop = useCallback(
        async (accepted) => {
            if (!accepted.length) return;
            setUploading(true);
            for (const f of accepted) {
                const fd = new FormData();
                fd.append("file", f);
                try {
                    const { data } = await api.post("/api/files/upload", fd, {
                        headers: { "Content-Type": "multipart/form-data" },
                    });
                    setFiles((prev) => [data, ...prev]);
                } catch (e) {
                    toast.error(`${f.name} — ${errMessage(e)}`);
                }
            }
            setUploading(false);
        },
        [],
    );

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        multiple: true,
        accept: {
            "application/pdf": [".pdf"],
            "image/png": [".png"],
            "image/jpeg": [".jpg", ".jpeg"],
            "image/webp": [".webp"],
            "text/csv": [".csv"],
            "text/plain": [".txt"],
        },
        maxSize: 200 * 1024 * 1024,
    });

    const removeFile = async (fid) => {
        try {
            await api.delete(`/api/files/${fid}`);
            setFiles((prev) => prev.filter((f) => f.id !== fid));
        } catch (e) {
            toast.error(errMessage(e));
        }
    };

    const runAi = async () => {
        if (!files.length) {
            toast.error("Upload at least one drawing first.");
            return;
        }
        if (rateLow <= 0 || rateHigh <= 0) {
            toast.error("Set both LOW and HIGH rates (> 0).");
            return;
        }
        setRunning(true);
        setResult(null);
        try {
            const { data } = await api.post("/api/estimation/ai-calculate", {
                role,
                rate_low: rateLow,
                rate_high: rateHigh,
                file_ids: files.map((f) => f.id),
            });
            setResult(data);
            toast.success("AI estimate ready.");
            loadHistory();
        } catch (e) {
            toast.error(errMessage(e));
        }
        setRunning(false);
    };

    const downloadPdf = async (eid) => {
        const token = tokenStore.getAccess();
        const url = `${process.env.REACT_APP_BACKEND_URL}/api/estimation/${eid}/pdf`;
        try {
            const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
            if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
            const blob = await resp.blob();
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = `StructMind_${role}_Estimate.pdf`;
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) {
            toast.error(errMessage(e));
        }
    };

    const removeEst = async (eid) => {
        try {
            await api.delete(`/api/estimation/${eid}`);
            loadHistory();
            if (result?.id === eid) setResult(null);
            toast.success("Estimate removed.");
        } catch (e) {
            toast.error(errMessage(e));
        }
    };

    const v = result?.result?.visible;
    const ai = v?.ai_extracted;

    return (
        <div className="min-h-full bg-background">
            <div className="border-b border-ink-line bg-white px-10 py-10">
                <div className="text-overline">Estimation</div>
                <h1 className="mt-2 font-heading text-5xl font-black leading-none tracking-tight text-navy">
                    Drawing-driven cost estimate
                </h1>
                <p className="mt-3 max-w-3xl text-ink-muted">
                    Upload your structural drawings, set your per-{role === "fabricator" ? "ton" : "drawing"} rate
                    band, and STRUCTMIND CORE returns a low → high cost range based on what it measures in your files.
                </p>
            </div>

            <div className="container-steel grid gap-8 py-10 lg:grid-cols-5">
                {/* LEFT — Inputs */}
                <section className="card-steel p-6 lg:col-span-3">
                    <div className="flex items-center justify-between">
                        <div className="font-heading text-xl font-bold uppercase tracking-tight text-navy">
                            <Calculator size={18} className="-mt-1 mr-2 inline text-gold" />
                            01 · Inputs
                        </div>
                        {isSuperAdmin && (
                            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                Role
                                <Select value={role} onValueChange={setRole}>
                                    <SelectTrigger
                                        data-testid="est-role-select"
                                        className="h-9 w-40 rounded-none border-ink-line font-mono text-[11px] uppercase"
                                    >
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="rounded-none">
                                        <SelectItem className="rounded-none font-mono text-[11px] uppercase" value="detailer">Detailer</SelectItem>
                                        <SelectItem className="rounded-none font-mono text-[11px] uppercase" value="fabricator">Fabricator</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                    </div>

                    {cannotRun ? (
                        <div
                            data-testid="estimation-locked"
                            className="mt-6 border border-dashed border-ink-line bg-background p-6 text-center"
                        >
                            <div className="font-heading text-base font-bold uppercase text-navy">
                                Estimation not enabled
                            </div>
                            <div className="mt-2 text-sm text-ink-muted">
                                Your super admin has not enabled the estimation feature for your
                                account. Reach out to them to request access.
                            </div>
                        </div>
                    ) : !schema ? (
                        <Skeleton className="mt-6 h-64 rounded-none" />
                    ) : (
                        <>
                            <div className="mt-2 text-sm text-ink-muted">{schema.subtitle}</div>

                            {/* Upload zone */}
                            <div
                                {...getRootProps()}
                                data-testid="est-dropzone"
                                className={`mt-6 cursor-pointer border-2 border-dashed p-8 text-center transition-colors ${
                                    isDragActive
                                        ? "border-gold bg-gold-pale"
                                        : "border-ink-line bg-background hover:border-navy hover:bg-gold-pale/40"
                                }`}
                            >
                                <input {...getInputProps()} data-testid="est-file-input" />
                                <CloudUpload size={40} className="mx-auto text-navy" strokeWidth={1.25} />
                                <div className="mt-3 font-heading text-lg font-black uppercase tracking-tight text-navy">
                                    Drop drawings here
                                </div>
                                <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                    PDF · PNG · JPG · WEBP · CSV · TXT · Multi-file OK
                                </div>
                            </div>

                            {/* File list */}
                            <div className="mt-3 space-y-2">
                                {uploading && (
                                    <div className="flex items-center gap-2 border border-gold bg-gold-pale px-3 py-2 font-mono text-xs uppercase tracking-wider text-navy">
                                        <span className="h-2 w-2 animate-pulse-ring rounded-full bg-gold" />
                                        Uploading…
                                    </div>
                                )}
                                {files.map((f) => (
                                    <div
                                        key={f.id}
                                        data-testid={`est-file-${f.id}`}
                                        className="flex items-center justify-between border border-ink-line bg-white px-3 py-2"
                                    >
                                        <div className="flex min-w-0 items-center gap-2">
                                            <FileIcon size={14} className="text-navy" />
                                            <div className="min-w-0">
                                                <div className="truncate font-heading text-sm font-semibold uppercase text-navy">
                                                    {f.original_name}
                                                </div>
                                                <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                                    {f.size_mb} MB
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="inline-flex items-center gap-1 border border-success px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-success">
                                                <CheckCircle2 size={10} />
                                                Ready
                                            </span>
                                            <button
                                                onClick={() => removeFile(f.id)}
                                                data-testid={`est-remove-${f.id}`}
                                                className="text-ink-muted hover:text-destructive"
                                                aria-label="Remove"
                                            >
                                                <Trash2 size={13} />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* LOW / HIGH rates (the only two manual inputs) */}
                            <div className="mt-6 grid gap-4 md:grid-cols-2">
                                <div className="border border-gold bg-gold-pale/60 p-3">
                                    <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">
                                        {schema.rate_label_low} <span className="text-destructive">*</span>
                                    </label>
                                    <Input
                                        data-testid="est-rate-low"
                                        type="number"
                                        value={rateLow}
                                        onChange={(e) => setRateLow(parseFloat(e.target.value || "0"))}
                                        min={1}
                                        className="h-11 rounded-none border-ink-line font-mono text-base focus-visible:border-gold focus-visible:ring-0"
                                    />
                                    <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                        {schema.rate_help_low}
                                    </div>
                                </div>
                                <div className="border border-gold bg-gold-pale/60 p-3">
                                    <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">
                                        {schema.rate_label_high} <span className="text-destructive">*</span>
                                    </label>
                                    <Input
                                        data-testid="est-rate-high"
                                        type="number"
                                        value={rateHigh}
                                        onChange={(e) => setRateHigh(parseFloat(e.target.value || "0"))}
                                        min={1}
                                        className="h-11 rounded-none border-ink-line font-mono text-base focus-visible:border-gold focus-visible:ring-0"
                                    />
                                    <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                        {schema.rate_help_high}
                                    </div>
                                </div>
                            </div>

                            <button
                                onClick={runAi}
                                disabled={running || uploading || !files.length}
                                data-testid="est-calculate-btn"
                                className="btn-gold mt-6 w-full"
                            >
                                <Sparkles size={14} />
                                {running ? "STRUCTMIND CORE is analysing your drawings…" : "Analyse drawings & calculate"}
                            </button>
                            {!files.length && (
                                <div className="mt-2 text-center font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                    Upload at least one drawing to enable the calculate button.
                                </div>
                            )}
                        </>
                    )}
                </section>

                {/* RIGHT — Result */}
                <section className="card-steel p-6 lg:col-span-2">
                    <div className="font-heading text-xl font-bold uppercase tracking-tight text-navy">
                        02 · Result
                    </div>
                    {!v ? (
                        <div className="mt-6 border border-dashed border-ink-line bg-background p-6 text-center text-sm text-ink-muted">
                            Upload a drawing + set your rate band, then hit Analyse.
                            STRUCTMIND CORE will extract quantities and apply your band.
                        </div>
                    ) : (
                        <motion.div
                            key={result.id}
                            initial={{ opacity: 0, y: 16 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.3 }}
                            className="mt-6 space-y-4"
                        >
                            <div className="border border-gold bg-gold-pale p-4">
                                <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                    Final range
                                </div>
                                <div className="font-heading text-2xl font-black uppercase tracking-tight text-navy">
                                    {v.grand_range_text}
                                </div>
                                <div className="mt-1 font-mono text-[11px] uppercase tracking-wider text-ink">
                                    Midpoint headline: <span className="text-navy">{v.final_amount}</span>
                                </div>
                            </div>

                            <div>
                                <div className="text-overline">AI extracted (STRUCTMIND CORE)</div>
                                <div className="mt-2 grid grid-cols-2 gap-2">
                                    {role === "fabricator" ? (
                                        <>
                                            <KV label="Tonnage"        value={`${ai?.tonnage ?? "—"} t`} testId="ai-tonnage" />
                                            <KV label="Members"        value={ai?.members_counted ?? "—"} />
                                            <KV label="Material"       value={ai?.primary_material || "—"} />
                                            <KV label="Drawings"       value={ai?.drawings_seen ?? "—"} />
                                        </>
                                    ) : (
                                        <>
                                            <KV label="Drawings"       value={ai?.drawings ?? "—"} testId="ai-drawings" />
                                            <KV label="Connections"    value={ai?.connections ?? "—"} />
                                            <KV label="Complexity"     value={ai?.complexity || "—"} />
                                            <KV label="Multiplier"     value={ai?.complexity_multiplier ? `×${ai.complexity_multiplier}` : "—"} />
                                        </>
                                    )}
                                </div>
                                <div className="mt-2 border border-ink-line bg-background p-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                    Confidence: {ai?.confidence?.toUpperCase() || "—"} · {ai?.notes}
                                </div>
                            </div>

                            <div>
                                <div className="text-overline">Range</div>
                                <table className="mt-2 w-full text-left text-sm">
                                    <tbody>
                                        <tr className="border-b border-ink-line">
                                            <td className="py-2 font-mono text-[11px] uppercase tracking-wider text-ink-muted">Low</td>
                                            <td className="py-2 text-right font-heading font-semibold text-navy">{v.grand_low}</td>
                                        </tr>
                                        <tr className="border-b border-ink-line bg-gold-pale">
                                            <td className="py-2 font-mono text-[11px] uppercase tracking-wider text-navy">Mid</td>
                                            <td className="py-2 text-right font-heading font-bold text-navy">{v.grand_mid}</td>
                                        </tr>
                                        <tr>
                                            <td className="py-2 font-mono text-[11px] uppercase tracking-wider text-ink-muted">High</td>
                                            <td className="py-2 text-right font-heading font-semibold text-navy">{v.grand_high}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>

                            <button
                                onClick={() => downloadPdf(result.id)}
                                data-testid="est-pdf-btn"
                                className="btn-ghost-navy w-full"
                            >
                                <Download size={14} />
                                Download PDF
                            </button>
                        </motion.div>
                    )}
                </section>
            </div>

            {/* HISTORY */}
            <div className="container-steel pb-16">
                <div className="card-steel">
                    <div className="flex items-center justify-between border-b border-ink-line px-6 py-4">
                        <div className="flex items-center gap-2 font-heading text-lg font-bold uppercase tracking-wide text-navy">
                            <History size={16} className="text-gold" /> Previous estimates
                        </div>
                        <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                            {history.length} on file
                        </div>
                    </div>
                    {!history.length ? (
                        <div className="p-10 text-center text-sm text-ink-muted">
                            No estimates yet — your saved estimates appear here.
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left">
                                <thead className="bg-background">
                                    <tr className="border-b border-ink-line">
                                        {["When", "Project", "Role", "Country", "Final", ""].map((h) => (
                                            <th
                                                key={h}
                                                className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted"
                                            >
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {history.map((e) => (
                                        <tr
                                            key={e.id}
                                            data-testid={`est-history-${e.id}`}
                                            className="border-b border-ink-line last:border-b-0"
                                        >
                                            <td className="whitespace-nowrap px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                                {new Date(e.created_at).toLocaleString()}
                                            </td>
                                            <td className="px-4 py-3 font-heading text-sm font-semibold uppercase text-navy">
                                                {e.project_name}
                                            </td>
                                            <td className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-navy">
                                                {e.role}
                                            </td>
                                            <td className="px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                                {e.country}
                                            </td>
                                            <td className="px-4 py-3 font-heading text-sm font-bold text-navy">
                                                {e.result?.visible?.final_amount || "—"}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
                                                    <button
                                                        onClick={() => downloadPdf(e.id)}
                                                        data-testid={`est-pdf-${e.id}`}
                                                        className="inline-flex items-center gap-1 border border-navy bg-white px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-navy hover:bg-navy hover:text-gold"
                                                    >
                                                        <Download size={10} />
                                                        PDF
                                                    </button>
                                                    <button
                                                        onClick={() => removeEst(e.id)}
                                                        data-testid={`est-delete-${e.id}`}
                                                        className="inline-flex items-center gap-1 border border-ink-line bg-white px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted hover:border-destructive hover:text-destructive"
                                                    >
                                                        <Trash2 size={10} />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function KV({ label, value, testId }) {
    return (
        <div className="border border-ink-line bg-white p-2" data-testid={testId}>
            <div className="font-mono text-[9px] uppercase tracking-wider text-ink-muted">
                {label}
            </div>
            <div className="mt-0.5 font-heading text-sm font-bold uppercase text-navy">{value}</div>
        </div>
    );
}
