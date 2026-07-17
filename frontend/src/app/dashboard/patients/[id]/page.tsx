"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { medications, patients } from "@/api/client";
import Link from "next/link";

interface Medication {
  id: string;
  name: string;
  dose_value: number;
  dose_unit: string;
  frequency_per_day: number;
  quantity_on_hand: number;
  days_remaining: number;
  refill_threshold_days: number;
  reminder_escalation_days: number;
  resolution_source: string;
  resolution_confidence: string;
  rxcui: string | null;
  is_active: boolean;
}

interface InteractionWarning {
  drug_a: string;
  drug_b: string;
  severity: string;
  description: string;
}

interface Patient {
  id: string;
  full_name: string;
  age?: number;
  notes?: string;
  telegram_chat_id?: number;
}

function DaysBar({ days, threshold }: { days: number; threshold: number }) {
  const pct = Math.min((days / (threshold * 3)) * 100, 100);
  const color =
    days <= 3 ? "bg-red-500" : days <= threshold ? "bg-amber-400" : "bg-emerald-400";
  return (
    <div className="w-full bg-slate-700/50 rounded-full h-1.5 mt-2">
      <div
        className={`h-1.5 rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, string> = {
    contraindicated: "bg-red-600/20 text-red-400 border-red-500/30",
    major: "bg-orange-600/20 text-orange-400 border-orange-500/30",
    moderate: "bg-amber-600/20 text-amber-400 border-amber-500/30",
    minor: "bg-slate-600/20 text-slate-400 border-slate-500/30",
  };
  return (
    <span
      className={`px-2 py-0.5 text-xs font-semibold border rounded-full uppercase ${
        map[severity] ?? map.minor
      }`}
    >
      {severity}
    </span>
  );
}

const FREQ_LABELS: Record<string, string> = {
  "0.5": "Every other day",
  "1": "Once daily",
  "2": "Twice daily",
  "3": "Three times daily",
  "4": "Four times daily",
};

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [medList, setMedList] = useState<Medication[]>([]);
  const [caregiversList, setCaregiversList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddMed, setShowAddMed] = useState(false);
  const [showAddCaregiver, setShowAddCaregiver] = useState(false);
  const [interactionWarnings, setInteractionWarnings] = useState<InteractionWarning[]>([]);
  const [saving, setSaving] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [newCaregiverEmail, setNewCaregiverEmail] = useState("");
  const [newCaregiverRole, setNewCaregiverRole] = useState("secondary");

  const handleCopy = async () => {
    if (!linkToken) return;
    try {
      await navigator.clipboard.writeText(`/link ${linkToken}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      alert("Failed to copy to clipboard.");
    }
  };

  const [newMed, setNewMed] = useState({
    name: "",
    dose_value: "",
    dose_unit: "mg",
    frequency_per_day: "1",
    quantity_on_hand: "",
    start_date: new Date().toISOString().split("T")[0],
    refill_threshold_days: "7",
    reminder_escalation_days: "3",
    notes: "",
  });

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      router.push("/login");
      return;
    }
    fetchData();
  }, [id]);

  const fetchData = async () => {
    try {
      const [patRes, medRes, cgRes] = await Promise.all([
        patients.get(id),
        medications.list(id),
        patients.listCaregivers(id),
      ]);
      setPatient(patRes.data);
      setMedList(medRes.data);
      setCaregiversList(cgRes.data);
    } catch {
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  };

  const handleAddCaregiverSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviting(true);
    try {
      await patients.addCaregiver(id, {
        caregiver_email: newCaregiverEmail,
        role: newCaregiverRole,
      });
      setNewCaregiverEmail("");
      setShowAddCaregiver(false);
      fetchData();
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Failed to add caregiver. Make sure they have a registered account.";
      alert(msg);
    } finally {
      setInviting(false);
    }
  };

  const handleAddMed = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setInteractionWarnings([]);
    try {
      const { data } = await medications.add(id, {
        ...newMed,
        dose_value: parseFloat(newMed.dose_value),
        frequency_per_day: parseFloat(newMed.frequency_per_day),
        quantity_on_hand: parseFloat(newMed.quantity_on_hand),
        refill_threshold_days: parseInt(newMed.refill_threshold_days),
        reminder_escalation_days: parseInt(newMed.reminder_escalation_days),
      });

      if (data.interaction_warnings?.length > 0) {
        setInteractionWarnings(data.interaction_warnings);
      } else {
        setShowAddMed(false);
        setNewMed({
          name: "", dose_value: "", dose_unit: "mg",
          frequency_per_day: "1", quantity_on_hand: "",
          start_date: new Date().toISOString().split("T")[0],
          refill_threshold_days: "7", reminder_escalation_days: "3", notes: "",
        });
      }
      fetchData();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(msg || "Failed to add medication.");
    } finally {
      setSaving(false);
    }
  };

  const handleGetLinkToken = async () => {
    try {
      const { data } = await patients.getLinkToken(id);
      setLinkToken(data.token);
    } catch {
      alert("Failed to generate link token.");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-slate-400 animate-pulse">Loading...</div>
      </div>
    );
  }

  const criticalMeds = medList.filter((m) => m.days_remaining <= m.reminder_escalation_days);
  const warningMeds = medList.filter(
    (m) => m.days_remaining > m.reminder_escalation_days && m.days_remaining <= m.refill_threshold_days
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center gap-4">
          <Link href="/dashboard" className="text-slate-400 hover:text-white transition text-sm">
            ← Dashboard
          </Link>
          <span className="text-slate-700">|</span>
          <h1 className="text-lg font-bold text-white">{patient?.full_name}</h1>
          {patient?.age && (
            <span className="text-slate-500 text-sm">Age {patient.age}</span>
          )}
          <div className="ml-auto flex gap-2">
            <Link
              href={`/dashboard/patients/${id}/scan`}
              className="px-3 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition"
            >
              📷 Scan Prescription
            </Link>
            <button
              id="add-med-btn"
              onClick={() => setShowAddMed(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition"
            >
              + Add Medication
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Telegram link status */}
        {!patient?.telegram_chat_id && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-5">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <p className="text-amber-400 font-semibold">⚠️ Telegram Alert Configuration</p>
                <p className="text-slate-400 text-sm mt-0.5">
                  Link this patient to a Telegram chat to receive automated refill alerts.
                </p>
              </div>
              {!linkToken ? (
                <button
                  id="generate-link-token-btn"
                  onClick={handleGetLinkToken}
                  className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl transition shadow-lg shadow-amber-500/10"
                >
                  Get Telegram Link Code
                </button>
              ) : (
                <div className="flex items-center gap-3 bg-slate-900/60 border border-slate-700/50 rounded-xl p-2.5">
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Bot Code</span>
                    <code className="text-emerald-400 font-mono font-bold text-lg leading-tight">
                      /link {linkToken}
                    </code>
                  </div>
                  <button
                    onClick={handleCopy}
                    className="p-2 bg-slate-800 hover:bg-slate-700 active:bg-slate-600 text-slate-300 hover:text-white rounded-lg border border-slate-700 transition flex items-center justify-center gap-1.5 min-w-[75px]"
                  >
                    {copied ? (
                      <>
                        <span className="text-xs text-emerald-400 font-medium">Copied!</span>
                      </>
                    ) : (
                      <>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" className="w-4 h-4">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 7.5V6.108c0-1.135.845-2.098 1.976-2.192.373-.03.748-.057 1.123-.08M15.75 18H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08M15.75 18.75v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5A3.375 3.375 0 0 0 6.375 7.5H5.25m11.9-3.664A2.251 2.251 0 0 0 15 2.25h-1.5a2.251 2.251 0 0 0-2.15 1.586m5.8 0c.065.21.1.433.1.664v.75h-6V4.5c0-.231.035-.454.1-.664M6.75 7.5H4.875c-.621 0-1.125.504-1.125 1.125v12c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V16.5a9 9 0 0 0-9-9Z" />
                        </svg>
                        <span className="text-xs font-medium">Copy</span>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Alert banners */}
        {criticalMeds.length > 0 && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
            <p className="text-red-400 font-semibold text-sm">
              🚨 Critical: {criticalMeds.map((m) => m.name).join(", ")} — refill immediately!
            </p>
          </div>
        )}
        {warningMeds.length > 0 && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
            <p className="text-amber-400 font-semibold text-sm">
              ⚠️ Refill soon: {warningMeds.map((m) => m.name).join(", ")}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* Medication table */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden shadow-lg">
              <div className="px-6 py-4 border-b border-slate-700/50 bg-slate-800/20">
                <h2 className="text-white font-semibold">Active Medications</h2>
              </div>

              {medList.length === 0 ? (
                <div className="text-center py-16 text-slate-500">
                  No medications yet. Click &quot;+ Add Medication&quot; to start tracking.
                </div>
              ) : (
                <div className="divide-y divide-slate-700/30 bg-slate-800/10">
                  {medList.map((med) => (
                    <div key={med.id} className="px-6 py-5 hover:bg-slate-800/30 transition">
                      <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-white font-semibold">{med.name}</h3>
                            {!med.rxcui && (
                              <span className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded-full">
                                ⚠️ Interaction check unavailable
                              </span>
                            )}
                          </div>
                          <p className="text-slate-400 text-sm mt-0.5">
                            {med.dose_value} {med.dose_unit} ·{" "}
                            {FREQ_LABELS[String(med.frequency_per_day)] ?? `${med.frequency_per_day}×/day`}
                          </p>
                          <p className="text-slate-500 text-sm mt-0.5">
                            Stock: {med.quantity_on_hand} {med.dose_unit}(s)
                          </p>
                          <DaysBar days={med.days_remaining} threshold={med.refill_threshold_days} />
                        </div>

                        <div className="text-right shrink-0">
                          <div
                            className={`text-2xl font-bold ${
                              med.days_remaining <= 3
                                ? "text-red-400"
                                : med.days_remaining <= med.refill_threshold_days
                                ? "text-amber-400"
                                : "text-emerald-400"
                            }`}
                          >
                            {med.days_remaining.toFixed(1)}d
                          </div>
                          <p className="text-slate-500 text-xs">remaining</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-1 space-y-6">
            {/* Caregivers panel */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 space-y-4 shadow-lg">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-semibold">Caregivers</h3>
                <button
                  id="invite-caregiver-btn"
                  onClick={() => setShowAddCaregiver(true)}
                  className="text-xs text-blue-400 hover:text-blue-300 font-semibold transition"
                >
                  + Add Caregiver
                </button>
              </div>
              <div className="divide-y divide-slate-700/30">
                {caregiversList.map((cg) => (
                  <div key={cg.id} className="py-3 flex items-center justify-between">
                    <div className="min-w-0 flex-1 pr-3">
                      <p className="text-slate-200 text-sm font-medium truncate">{cg.full_name}</p>
                      <p className="text-slate-500 text-xs truncate">{cg.email}</p>
                    </div>
                    <span className="text-[9px] tracking-wider uppercase font-bold px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-300 shrink-0">
                      {cg.role}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Add Medication Modal */}
      {showAddMed && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-start justify-center z-50 p-4 overflow-y-auto">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 w-full max-w-lg shadow-2xl my-8">
            <h2 className="text-xl font-bold text-white mb-6">Add Medication</h2>

            {/* Interaction warnings */}
            {interactionWarnings.length > 0 && (
              <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl space-y-3">
                <p className="text-red-400 font-semibold text-sm">⚠️ Drug Interaction Warnings</p>
                {interactionWarnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <SeverityBadge severity={w.severity} />
                    <div>
                      <p className="text-slate-300 text-sm font-medium">
                        {w.drug_a} + {w.drug_b}
                      </p>
                      <p className="text-slate-500 text-xs mt-0.5">{w.description}</p>
                    </div>
                  </div>
                ))}
                <button
                  onClick={() => {
                    setInteractionWarnings([]);
                    setShowAddMed(false);
                  }}
                  className="mt-2 text-sm text-slate-400 hover:text-white transition"
                >
                  Close
                </button>
              </div>
            )}

            <form onSubmit={handleAddMed} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Drug Name *</label>
                <input
                  id="med-name"
                  type="text"
                  required
                  value={newMed.name}
                  onChange={(e) => setNewMed({ ...newMed, name: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  placeholder="e.g. Ecosprin 75mg"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Dose Amount *</label>
                  <input
                    id="med-dose-value"
                    type="number"
                    required
                    min="0.01"
                    step="0.01"
                    value={newMed.dose_value}
                    onChange={(e) => setNewMed({ ...newMed, dose_value: e.target.value })}
                    className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                    placeholder="e.g. 75"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Unit *</label>
                  <select
                    id="med-dose-unit"
                    value={newMed.dose_unit}
                    onChange={(e) => setNewMed({ ...newMed, dose_unit: e.target.value })}
                    className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  >
                    <option>mg</option>
                    <option>ml</option>
                    <option>tablet</option>
                    <option>capsule</option>
                    <option>IU</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Frequency *</label>
                  <select
                    id="med-frequency"
                    value={newMed.frequency_per_day}
                    onChange={(e) => setNewMed({ ...newMed, frequency_per_day: e.target.value })}
                    className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  >
                    <option value="0.5">Every other day</option>
                    <option value="1">Once daily</option>
                    <option value="2">Twice daily</option>
                    <option value="3">Three times daily</option>
                    <option value="4">Four times daily</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Qty on Hand *</label>
                  <input
                    id="med-quantity"
                    type="number"
                    required
                    min="0"
                    value={newMed.quantity_on_hand}
                    onChange={(e) => setNewMed({ ...newMed, quantity_on_hand: e.target.value })}
                    className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                    placeholder="e.g. 30"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Start Date *</label>
                <input
                  id="med-start-date"
                  type="date"
                  required
                  value={newMed.start_date}
                  onChange={(e) => setNewMed({ ...newMed, start_date: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Alert threshold (days)</label>
                  <input
                    id="med-threshold"
                    type="number"
                    min="1"
                    value={newMed.refill_threshold_days}
                    onChange={(e) => setNewMed({ ...newMed, refill_threshold_days: e.target.value })}
                    className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Escalation (days)</label>
                  <input
                    id="med-escalation"
                    type="number"
                    min="1"
                    value={newMed.reminder_escalation_days}
                    onChange={(e) => setNewMed({ ...newMed, reminder_escalation_days: e.target.value })}
                    className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowAddMed(false); setInteractionWarnings([]); }}
                  className="flex-1 py-3 text-slate-400 hover:text-white border border-slate-600 rounded-xl transition"
                >
                  Cancel
                </button>
                <button
                  id="save-med-btn"
                  type="submit"
                  disabled={saving}
                  className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition"
                >
                  {saving ? "Checking interactions..." : "Add Medication"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Add Caregiver Modal */}
      {showAddCaregiver && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 w-full max-w-md shadow-2xl">
            <h2 className="text-xl font-bold text-white mb-6">Add Co-Caregiver</h2>
            <form onSubmit={handleAddCaregiverSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5 font-semibold">
                  Caregiver's Registered Email *
                </label>
                <input
                  id="caregiver-email-input"
                  type="email"
                  required
                  value={newCaregiverEmail}
                  onChange={(e) => setNewCaregiverEmail(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  placeholder="brother@example.com"
                />
                <p className="text-slate-500 text-xs mt-1.5">
                  Your co-caregiver must already have registered an account on this platform.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5 font-semibold">
                  Role *
                </label>
                <select
                  id="caregiver-role-select"
                  value={newCaregiverRole}
                  onChange={(e) => setNewCaregiverRole(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                >
                  <option value="primary">Primary Caregiver</option>
                  <option value="secondary">Secondary Caregiver</option>
                </select>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddCaregiver(false)}
                  className="flex-1 py-3 text-slate-400 hover:text-white border border-slate-600 rounded-xl transition"
                >
                  Cancel
                </button>
                <button
                  id="submit-caregiver-btn"
                  type="submit"
                  disabled={inviting}
                  className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition"
                >
                  {inviting ? "Adding..." : "Add Caregiver"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
