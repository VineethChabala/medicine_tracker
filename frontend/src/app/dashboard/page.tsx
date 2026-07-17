"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { patients } from "@/api/client";
import Link from "next/link";

interface Patient {
  id: string;
  full_name: string;
  age?: number;
  notes?: string;
  telegram_chat_id?: number;
}

function DaysRemainingBadge({ days }: { days: number }) {
  if (days <= 3)
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/20">
        🔴 {days.toFixed(1)}d left
      </span>
    );
  if (days <= 7)
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/20">
        🟡 {days.toFixed(1)}d left
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
      🟢 {days.toFixed(1)}d left
    </span>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [patientList, setPatientList] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddPatient, setShowAddPatient] = useState(false);
  const [newPatient, setNewPatient] = useState({ full_name: "", age: "", notes: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login");
      return;
    }
    fetchPatients();
  }, []);

  const fetchPatients = async () => {
    try {
      const { data } = await patients.list();
      setPatientList(data);
    } catch {
      router.push("/login");
    } finally {
      setLoading(false);
    }
  };

  const handleAddPatient = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await patients.create({
        full_name: newPatient.full_name,
        age: newPatient.age ? parseInt(newPatient.age) : undefined,
        notes: newPatient.notes || undefined,
      });
      setNewPatient({ full_name: "", age: "", notes: "" });
      setShowAddPatient(false);
      fetchPatients();
    } catch {
      alert("Failed to add patient. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    localStorage.clear();
    router.push("/login");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-slate-400 text-lg animate-pulse">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">💊</span>
            <h1 className="text-xl font-bold text-white">Medicine Refill Tracker</h1>
          </div>
          <div className="flex items-center gap-3">
            <button
              id="add-patient-btn"
              onClick={() => setShowAddPatient(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition"
            >
              + Add Patient
            </button>
            <button
              id="logout-btn"
              onClick={handleLogout}
              className="px-4 py-2 text-slate-400 hover:text-white text-sm transition"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {/* Stats row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5">
            <p className="text-slate-400 text-sm">Total Patients</p>
            <p className="text-3xl font-bold text-white mt-1">{patientList.length}</p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5">
            <p className="text-slate-400 text-sm">Linked to Telegram</p>
            <p className="text-3xl font-bold text-emerald-400 mt-1">
              {patientList.filter((p) => p.telegram_chat_id).length}
            </p>
          </div>
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5">
            <p className="text-slate-400 text-sm">Not Linked</p>
            <p className="text-3xl font-bold text-amber-400 mt-1">
              {patientList.filter((p) => !p.telegram_chat_id).length}
            </p>
          </div>
        </div>

        {/* Patient cards */}
        {patientList.length === 0 ? (
          <div className="text-center py-24">
            <p className="text-6xl mb-4">🏥</p>
            <p className="text-slate-400 text-lg">No patients yet.</p>
            <p className="text-slate-500 text-sm mt-1">Click &quot;+ Add Patient&quot; to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {patientList.map((patient) => (
              <Link
                key={patient.id}
                href={`/dashboard/patients/${patient.id}`}
                id={`patient-card-${patient.id}`}
                className="group block bg-slate-800/50 hover:bg-slate-800 border border-slate-700/50 hover:border-blue-500/30 rounded-xl p-6 transition-all duration-200 shadow-lg hover:shadow-blue-500/10"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 rounded-full bg-blue-500/20 border border-blue-500/30 flex items-center justify-center text-lg">
                    {patient.full_name.charAt(0).toUpperCase()}
                  </div>
                  {patient.telegram_chat_id ? (
                    <span className="text-xs text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded-full">
                      ✓ Telegram
                    </span>
                  ) : (
                    <span className="text-xs text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
                      ! Not linked
                    </span>
                  )}
                </div>
                <h3 className="text-white font-semibold text-lg group-hover:text-blue-300 transition">
                  {patient.full_name}
                </h3>
                {patient.age && (
                  <p className="text-slate-500 text-sm mt-0.5">Age: {patient.age}</p>
                )}
                {patient.notes && (
                  <p className="text-slate-500 text-sm mt-2 line-clamp-2">{patient.notes}</p>
                )}
                <p className="text-blue-400 text-sm mt-4 font-medium group-hover:translate-x-1 transition-transform">
                  View medications →
                </p>
              </Link>
            ))}
          </div>
        )}
      </main>

      {/* Add Patient Modal */}
      {showAddPatient && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 w-full max-w-md shadow-2xl">
            <h2 className="text-xl font-bold text-white mb-6">Add New Patient</h2>
            <form onSubmit={handleAddPatient} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Full Name *
                </label>
                <input
                  id="new-patient-name"
                  type="text"
                  required
                  value={newPatient.full_name}
                  onChange={(e) => setNewPatient({ ...newPatient, full_name: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  placeholder="Patient's full name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Age</label>
                <input
                  id="new-patient-age"
                  type="number"
                  min="0"
                  max="150"
                  value={newPatient.age}
                  onChange={(e) => setNewPatient({ ...newPatient, age: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition"
                  placeholder="e.g. 68"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Notes</label>
                <textarea
                  id="new-patient-notes"
                  rows={3}
                  value={newPatient.notes}
                  onChange={(e) => setNewPatient({ ...newPatient, notes: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition resize-none"
                  placeholder="Medical conditions, allergies..."
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddPatient(false)}
                  className="flex-1 py-3 text-slate-400 hover:text-white border border-slate-600 rounded-xl transition"
                >
                  Cancel
                </button>
                <button
                  id="save-patient-btn"
                  type="submit"
                  disabled={saving}
                  className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition"
                >
                  {saving ? "Saving..." : "Add Patient"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
