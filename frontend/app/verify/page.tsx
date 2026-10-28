import type { Metadata } from "next";
import Link from "next/link";
import AttestationVerifier from "@/components/AttestationVerifier";
import { ShieldCheck, Cpu, ArrowLeft } from "lucide-react";

export const metadata: Metadata = {
  title: "Independent Attestation Verifier · ApexMarket",
  description:
    "Zero-backend-dependency client-side cryptographic attestation and proof audit verification portal for enterprise batch workloads.",
};

export default function VerifyPage() {
  return (
    <div className="min-h-screen bg-[#0a0f18] text-slate-100 flex flex-col selection:bg-[#70e4bf33]">
      {/* Top Navigation Bar */}
      <header className="w-full border-b border-[#202c3c] bg-[#0c121e]/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2 group">
              <span className="font-mono text-base font-black tracking-tight text-white group-hover:text-[#70e4bf] transition-colors">
                <span className="text-white">Apex</span>
                <span className="text-[#70e4bf]">Market</span>
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-[#70e4bf1a] text-[#70e4bf] border border-[#70e4bf33]">
                Audit Portal
              </span>
            </Link>

            <nav className="hidden md:flex items-center gap-4 text-xs font-semibold text-slate-400">
              <Link href="/dashboard" className="hover:text-slate-200 transition-colors">
                Mission Control
              </Link>
              <Link href="/architecture" className="hover:text-slate-200 transition-colors">
                System Architecture
              </Link>
              <Link href="/verify" className="text-[#70e4bf]">
                Verify Audit Bundle
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#1a2638] hover:bg-[#23334c] text-slate-200 border border-[#2a3c54] transition-colors"
            >
              <Cpu size={14} className="text-[#70e4bf]" /> Launch Cluster
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        <AttestationVerifier />
      </main>
    </div>
  );
}
