"use client";
import Topology from "./Topology";
import type { Provider, Snapshot } from "@/lib/types";

export interface SwarmTopologyGraphProps {
  providers: Provider[];
  snapshot: Snapshot;
  confidential: boolean;
}

/**
 * SwarmTopologyGraph renders the live network topology between the ApexMarket
 * central router, verified anchor, and registered compute spot providers.
 */
export default function SwarmTopologyGraph(props: SwarmTopologyGraphProps) {
  return <Topology {...props} />;
}
