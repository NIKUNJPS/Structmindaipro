import { useEffect, useMemo, useState } from "react";
import { Calculator, Download, History, Plus, Sparkles, Trash2 } from "lucide-react";
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
    const [role, setRole] = useState(user?.role === "super_admin" ? "detailer" : user?.role || "detailer");
    const [country, setCountry] = useState("USA");
    const [countries, setCountries] = useState([]);
    const [schema, setSchema] = useState(null);
    const [inputs, setInputs] = useState({});
    const [projectName, setProjectName] = useState("Quick Estimate");
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [history, setHistory] = useState([]);

    useEffect(() => {
        (async () => {
            try {
                const { data } = await api.get("/api/estimation/countries");
                setCountries(data.countries || []);
                if (data.countries?.length && !data.countries.find((c) => c.code === country)) {
                    setCountry(data.countries[0].code);
                }
            } catch (e) {
                toast.error(errMessage(e));
            }
        })();
    }, []);

    useEffect(() => {
        if (!role) return;
        (async () => {
            try {
                const { data } = await api.get(`/api/estimation/schema/${role}`);
                setSchema(data.schema);
                const initial = {};
                for (const f of data.schema.fields) initial[f.key] = f.default;
                setInputs(initial);
            } catch (e) {
                toast.error(errMessage(e));
                setSchema(null);
            }
        })();
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

    const set = (k, v) => setInputs((p) => ({ ...p, [k]: v }));

    const submit = async () => {
        setRunning(true);
        setResult(null);
        try {
            const { data } = await api.post("/api/estimation/calculate", {
                role,
                country,
                project_name: projectName,
                inputs,
            });
            setResult(data);
            toast.success("Estimate calculated.");
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

    const visibleResult = useMemo(() => result?.result?.visible, [result]);

    return (
        <div className="min-h-full bg-background">
            <div className="border-b border-ink-line bg-white px-10 py-10">
                <div className="text-overline">Estimation</div>
                <h1 className="mt-2 font-heading text-5xl font-black leading-none tracking-tight text-navy">
                    Cost estimation
                </h1>
                <p className="mt-3 max-w-3xl text-ink-muted">
                    Deterministic role-specific estimates. Fabricators bid against their own per-ton
                    cost band; the engine returns a low → high range so commercial reviewers see the
                    full risk envelope.
                </p>
            </div>

            <div className="container-steel grid gap-8 py-10 lg:grid-cols-5">
                {/* LEFT — Form */}
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
                            <div className="mt-1 text-sm text-ink-muted">{schema.subtitle}</div>

                            <div className="mt-6 grid gap-4 md:grid-cols-2">
                                <div>
                                    <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">
                                        Project name
                                    </label>
                                    <Input
                                        data-testid="est-project-name"
                                        value={projectName}
                                        onChange={(e) => setProjectName(e.target.value)}
                                        className="h-10 rounded-none border-ink-line focus-visible:border-gold focus-visible:ring-0"
                                    />
                                </div>
                                <div>
                                    <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">
                                        Country
                                    </label>
                                    <Select value={country} onValueChange={setCountry}>
                                        <SelectTrigger
                                            data-testid="est-country-select"
                                            className="h-10 rounded-none border-ink-line font-mono text-[11px] uppercase"
                                        >
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="rounded-none">
                                            {countries.map((c) => (
                                                <SelectItem
                                                    key={c.code}
                                                    value={c.code}
                                                    className="rounded-none font-mono text-[11px] uppercase"
                                                >
                                                    {c.code} ({c.currency})
                                                </SelectItem>
                                            ))}
                                            {!countries.length && (
                                                <SelectItem
                                                    value="__none__"
                                                    disabled
                                                    className="rounded-none font-mono text-[11px] uppercase"
                                                >
                                                    No countries enabled
                                                </SelectItem>
                                            )}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {schema.fields.map((f) => (
                                    <div key={f.key} className={f.key.startsWith("cost_per_ton") ? "border border-gold bg-gold-pale/60 p-3" : ""}>
                                        <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">
                                            {f.label} {f.required && <span className="text-destructive">*</span>}
                                        </label>
                                        {f.type === "select" ? (
                                            <Select
                                                value={String(inputs[f.key] ?? f.default)}
                                                onValueChange={(v) => set(f.key, v)}
                                            >
                                                <SelectTrigger
                                                    data-testid={`est-field-${f.key}`}
                                                    className="h-10 rounded-none border-ink-line font-mono text-[11px] uppercase"
                                                >
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="rounded-none">
                                                    {f.options.map((o) => (
                                                        <SelectItem
                                                            key={o}
                                                            value={o}
                                                            className="rounded-none font-mono text-[11px] uppercase"
                                                        >
                                                            {o}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        ) : (
                                            <Input
                                                data-testid={`est-field-${f.key}`}
                                                type="number"
                                                value={inputs[f.key] ?? f.default}
                                                onChange={(e) => set(f.key, parseFloat(e.target.value || "0"))}
                                                min={f.min}
                                                max={f.max}
                                                className="h-10 rounded-none border-ink-line font-mono text-sm focus-visible:border-gold focus-visible:ring-0"
                                            />
                                        )}
                                        {f.help && (
                                            <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                                {f.help}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>

                            <button
                                onClick={submit}
                                disabled={running}
                                data-testid="est-calculate-btn"
                                className="btn-gold mt-6 w-full"
                            >
                                <Sparkles size={14} />
                                {running ? "Calculating…" : "Calculate estimate"}
                            </button>
                        </>
                    )}
                </section>

                {/* RIGHT — Result */}
                <section className="card-steel p-6 lg:col-span-2">
                    <div className="font-heading text-xl font-bold uppercase tracking-tight text-navy">
                        02 · Result
                    </div>
                    {!visibleResult ? (
                        <div className="mt-6 border border-dashed border-ink-line bg-background p-6 text-center text-sm text-ink-muted">
                            Run a calculation to see the breakdown here.
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
                                    Final amount
                                </div>
                                <div className="font-heading text-3xl font-black uppercase tracking-tight text-navy">
                                    {visibleResult.final_amount}
                                </div>
                                {visibleResult.grand_range_text && (
                                    <div className="mt-1 font-mono text-[11px] uppercase tracking-wider text-ink">
                                        Range: {visibleResult.grand_range_text}
                                    </div>
                                )}
                            </div>

                            {role === "fabricator" && visibleResult.process_breakdown && (
                                <div>
                                    <div className="mb-2 text-overline">Process split (mid)</div>
                                    <table className="w-full text-left text-sm">
                                        <tbody>
                                            {visibleResult.process_breakdown.map((p) => (
                                                <tr
                                                    key={p.process}
                                                    className="border-b border-ink-line last:border-b-0"
                                                >
                                                    <td className="py-2 font-mono text-[11px] uppercase tracking-wider text-ink-muted">
                                                        {p.process}
                                                    </td>
                                                    <td className="py-2 text-right font-mono text-xs text-ink-muted">
                                                        {p.share}
                                                    </td>
                                                    <td className="py-2 text-right font-heading text-sm font-semibold text-navy">
                                                        {p.amount}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}

                            {role === "detailer" && (
                                <div className="space-y-2 text-sm">
                                    <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                        Total hours
                                    </div>
                                    <div className="font-heading text-lg font-bold text-navy">
                                        {visibleResult.total_hours} hrs · {visibleResult.timeline_weeks} weeks
                                    </div>
                                    <div className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                                        {visibleResult.scope_summary}
                                    </div>
                                </div>
                            )}

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
