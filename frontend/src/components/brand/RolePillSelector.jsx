import { HardHat, Wrench, Ruler, Calculator, Factory, Network } from "lucide-react";

export const ROLES = [
    { id: "detailer", label: "Detailer", icon: Ruler },
    { id: "modular", label: "Modular", icon: Network },
    { id: "fabricator", label: "Fabricator", icon: Factory },
    { id: "engineer", label: "Engineer", icon: HardHat },
    { id: "pm", label: "Project Manager", icon: Wrench },
    { id: "estimator", label: "Estimator", icon: Calculator },
];

export function RolePillSelector({ value, onChange, testIdPrefix = "role" }) {
    return (
        <div
            data-testid="role-pill-selector"
            className="flex w-full flex-wrap gap-2"
        >
            {ROLES.map((r) => {
                const active = value === r.id;
                const Icon = r.icon;
                return (
                    <button
                        key={r.id}
                        type="button"
                        onClick={() => onChange(r.id)}
                        data-testid={`${testIdPrefix}-${r.id}`}
                        className={`inline-flex items-center gap-2 border px-3 py-2 font-mono text-[11px] uppercase tracking-wider transition-all ${
                            active
                                ? "border-gold bg-gold text-navy"
                                : "border-ink-line bg-white text-ink-muted hover:border-navy hover:text-navy"
                        }`}
                    >
                        <Icon size={14} strokeWidth={2} />
                        {r.label}
                    </button>
                );
            })}
        </div>
    );
}
