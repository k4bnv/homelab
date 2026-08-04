import type { ComparisonRow } from "@/components/SideBySideTable";
import { formatUsd, getAveragePriceForGpu, getAverageSpotPriceForGpu, getMinPriceForProvider } from "@/lib/data";
import type { FaqItem, GPU, Provider } from "@/types";

/**
 * All the templated copy + row data for a `/compare/[a]-vs-[b]/` page:
 * the side-by-side spec table, the "AI Verdict" one-liner, pros/cons, and
 * FAQ — built entirely from `gpus.json` / `providers.json` so every one of
 * the ~20 generated pages gets unique, data-driven content with no
 * hand-written copy per pair.
 */

function winnerFor(a: number, b: number, lowerIsBetter: boolean): "a" | "b" | "tie" {
  if (a === b) return "tie";
  const aWins = lowerIsBetter ? a < b : a > b;
  return aWins ? "a" : "b";
}

/** Like `winnerFor`, but treats "offers it at all" as beating "doesn't offer it". */
function nullableWinnerFor(a: number | null, b: number | null, lowerIsBetter: boolean): "a" | "b" | "tie" {
  if (a === null && b === null) return "tie";
  if (a === null) return "b";
  if (b === null) return "a";
  return winnerFor(a, b, lowerIsBetter);
}

// ---------------------------------------------------------------------------
// GPU vs GPU
// ---------------------------------------------------------------------------

export function buildGpuComparisonRows(a: GPU, b: GPU): ComparisonRow[] {
  const avgA = getAveragePriceForGpu(a.id);
  const avgB = getAveragePriceForGpu(b.id);
  const spotA = getAverageSpotPriceForGpu(a.id);
  const spotB = getAverageSpotPriceForGpu(b.id);

  const rows: ComparisonRow[] = [
    {
      label: "VRAM",
      valueA: `${a.vram_gb}GB ${a.vram_type}`,
      valueB: `${b.vram_gb}GB ${b.vram_type}`,
      winner: winnerFor(a.vram_gb, b.vram_gb, false),
    },
    {
      label: "Architecture",
      valueA: a.architecture,
      valueB: b.architecture,
      winner: "tie",
    },
    {
      label: "Avg. On-Demand Price",
      valueA: avgA ? `${formatUsd(avgA)}/hr` : "—",
      valueB: avgB ? `${formatUsd(avgB)}/hr` : "—",
      winner: avgA && avgB ? winnerFor(avgA, avgB, true) : "tie",
    },
    {
      label: "Avg. Spot Price",
      valueA: spotA !== null ? `${formatUsd(spotA)}/hr` : "Not offered",
      valueB: spotB !== null ? `${formatUsd(spotB)}/hr` : "Not offered",
      winner: nullableWinnerFor(spotA, spotB, true),
    },
    {
      label: "Power Draw (TDP)",
      valueA: `${a.tdp_watts}W`,
      valueB: `${b.tdp_watts}W`,
      winner: winnerFor(a.tdp_watts, b.tdp_watts, true),
    },
    {
      label: "Optimal Task",
      valueA: a.target_tasks[0] ?? "—",
      valueB: b.target_tasks[0] ?? "—",
      winner: "tie",
    },
  ];

  return rows;
}

export interface VerdictResult {
  text: string;
  strongerId: string;
  cheaperId: string;
}

export function buildGpuVerdict(a: GPU, b: GPU): VerdictResult {
  const avgA = getAveragePriceForGpu(a.id);
  const avgB = getAveragePriceForGpu(b.id);
  const powerScoreA = a.fp16_tflops ?? a.vram_gb;
  const powerScoreB = b.fp16_tflops ?? b.vram_gb;

  const stronger = powerScoreA >= powerScoreB ? a : b;
  const cheaper = avgA <= avgB ? a : b;
  const other = (entity: GPU) => (entity.id === a.id ? b : a);

  if (stronger.id === cheaper.id) {
    const alt = other(stronger);
    return {
      text: `Choose ${stronger.name} for the best all-round balance of performance and price for ${stronger.target_tasks[0] ?? "most workloads"}. Choose ${alt.name} if ${
        alt.vram_gb > stronger.vram_gb
          ? `you specifically need its extra ${alt.vram_gb}GB of VRAM`
          : `you're set up for ${alt.target_tasks[0] ?? "a different workload"}`
      }.`,
      strongerId: stronger.id,
      cheaperId: cheaper.id,
    };
  }

  // Avoid saying the same task twice ("...for LLM Training. Choose X for LLM Training...")
  // when both cards share the same primary use case.
  const sameTask = stronger.target_tasks[0] === cheaper.target_tasks[0];
  return {
    text: `Choose ${stronger.name} if you need maximum performance for ${
      stronger.target_tasks[0] ?? "demanding workloads"
    }. Choose ${cheaper.name} for ${
      sameTask ? "the same workload at a lower hourly rate" : `cost-effective ${cheaper.target_tasks[0] ?? "workloads"} at a lower hourly rate`
    }.`,
    strongerId: stronger.id,
    cheaperId: cheaper.id,
  };
}

export interface ProsCons {
  pros: string[];
  cons: string[];
}

export function buildGpuProsCons(subject: GPU, other: GPU): ProsCons {
  const avgSubject = getAveragePriceForGpu(subject.id);
  const avgOther = getAveragePriceForGpu(other.id);
  const pros: string[] = [];
  const cons: string[] = [];

  if (subject.vram_gb > other.vram_gb) {
    pros.push(`${subject.vram_gb - other.vram_gb}GB more VRAM than ${other.name} — room for larger models or batch sizes`);
  } else if (subject.vram_gb < other.vram_gb) {
    cons.push(`${other.vram_gb - subject.vram_gb}GB less VRAM than ${other.name} — may need sharding for large models`);
  }

  if (avgSubject && avgOther) {
    if (avgSubject < avgOther) {
      pros.push(`Cheaper on average (${formatUsd(avgSubject)}/hr vs ${formatUsd(avgOther)}/hr)`);
    } else if (avgSubject > avgOther) {
      cons.push(`Pricier on average (${formatUsd(avgSubject)}/hr vs ${formatUsd(avgOther)}/hr)`);
    }
  }

  if (subject.nvlink && !other.nvlink) {
    pros.push("NVLink support for efficient multi-GPU scaling on distributed jobs");
  } else if (!subject.nvlink && other.nvlink) {
    cons.push("No NVLink — multi-GPU jobs fall back to slower PCIe interconnect");
  }

  if (subject.tdp_watts < other.tdp_watts) {
    pros.push(`Lower power draw (${subject.tdp_watts}W vs ${other.tdp_watts}W) — cheaper to run at scale`);
  } else if (subject.tdp_watts > other.tdp_watts) {
    cons.push(`Higher power draw (${subject.tdp_watts}W vs ${other.tdp_watts}W)`);
  }

  if (subject.release_year > other.release_year) {
    pros.push(`Newer ${subject.architecture} architecture (${subject.release_year}) with better performance-per-watt`);
  } else if (subject.release_year < other.release_year) {
    cons.push(`Older ${subject.architecture} architecture (${subject.release_year})`);
  }

  if (pros.length === 0) pros.push(`Purpose-built for ${subject.target_tasks[0] ?? "its target workload"}`);
  if (cons.length === 0) cons.push("No major drawback versus the alternative — pick based on task fit");

  return { pros, cons };
}

// ---------------------------------------------------------------------------
// Provider vs Provider
// ---------------------------------------------------------------------------

const RISK_ORDER: Record<Provider["interruption_risk"], number> = {
  None: 0,
  Low: 1,
  Medium: 2,
  High: 3,
};

export function buildProviderComparisonRows(a: Provider, b: Provider): ComparisonRow[] {
  const minA = getMinPriceForProvider(a.slug);
  const minB = getMinPriceForProvider(b.slug);

  return [
    {
      label: "Lowest Price",
      valueA: `${formatUsd(minA)}/hr`,
      valueB: `${formatUsd(minB)}/hr`,
      winner: winnerFor(minA, minB, true),
    },
    {
      label: "Cloud Type",
      valueA: a.cloud_type,
      valueB: b.cloud_type,
      winner: "tie",
    },
    {
      label: "Storage Cost",
      valueA: `${formatUsd(a.storage_cost_per_gb, 2)}/GB/mo`,
      valueB: `${formatUsd(b.storage_cost_per_gb, 2)}/GB/mo`,
      winner: winnerFor(a.storage_cost_per_gb, b.storage_cost_per_gb, true),
    },
    {
      label: "Egress Cost",
      valueA: a.egress_cost_per_gb === 0 ? "Free" : `${formatUsd(a.egress_cost_per_gb, 2)}/GB`,
      valueB: b.egress_cost_per_gb === 0 ? "Free" : `${formatUsd(b.egress_cost_per_gb, 2)}/GB`,
      winner: winnerFor(a.egress_cost_per_gb, b.egress_cost_per_gb, true),
    },
    {
      label: "API / CLI",
      valueA: a.has_api_cli ? "Yes" : "No",
      valueB: b.has_api_cli ? "Yes" : "No",
      winner: a.has_api_cli === b.has_api_cli ? "tie" : a.has_api_cli ? "a" : "b",
    },
    {
      label: "User Rating",
      valueA: `★ ${a.rating.toFixed(1)} (${a.review_count.toLocaleString()})`,
      valueB: `★ ${b.rating.toFixed(1)} (${b.review_count.toLocaleString()})`,
      winner: winnerFor(a.rating, b.rating, false),
    },
  ];
}

export function buildProviderVerdict(a: Provider, b: Provider): VerdictResult {
  const minA = getMinPriceForProvider(a.slug);
  const minB = getMinPriceForProvider(b.slug);
  const reliable = RISK_ORDER[a.interruption_risk] <= RISK_ORDER[b.interruption_risk] ? a : b;
  const cheap = minA <= minB ? a : b;
  const other = (entity: Provider) => (entity.slug === a.slug ? b : a);

  if (reliable.slug === cheap.slug) {
    const alt = other(reliable);
    return {
      text: `Choose ${reliable.name} for the best mix of reliability and price. Choose ${alt.name} if you specifically want ${
        alt.cloud_type === "Community" ? "community/peer-to-peer hardware at the lowest possible spot rate" : "a dedicated secure-cloud provider"
      }.`,
      strongerId: reliable.slug,
      cheaperId: cheap.slug,
    };
  }

  return {
    text: `Choose ${reliable.name} for guaranteed instances and ${
      reliable.interruption_risk === "None" ? "zero interruption risk" : "lower interruption risk"
    }. Choose ${cheap.name} for the lowest ${cheap.cloud_type === "Community" ? "spot prices on community hardware" : "hourly rates"}.`,
    strongerId: reliable.slug,
    cheaperId: cheap.slug,
  };
}

export function buildProviderProsCons(subject: Provider, other: Provider): ProsCons {
  const minSubject = getMinPriceForProvider(subject.slug);
  const minOther = getMinPriceForProvider(other.slug);
  const pros: string[] = [];
  const cons: string[] = [];

  if (minSubject < minOther) {
    pros.push(`Lower entry price (from ${formatUsd(minSubject)}/hr vs ${formatUsd(minOther)}/hr)`);
  } else if (minSubject > minOther) {
    cons.push(`Higher entry price (from ${formatUsd(minSubject)}/hr vs ${formatUsd(minOther)}/hr)`);
  }

  if (RISK_ORDER[subject.interruption_risk] < RISK_ORDER[other.interruption_risk]) {
    pros.push(`Lower interruption risk (${subject.interruption_risk.toLowerCase()}) — safer for long-running jobs`);
  } else if (RISK_ORDER[subject.interruption_risk] > RISK_ORDER[other.interruption_risk]) {
    cons.push(`Higher interruption risk (${subject.interruption_risk.toLowerCase()}) on interruptible instances`);
  }

  if (subject.egress_cost_per_gb < other.egress_cost_per_gb) {
    pros.push(`Cheaper egress (${subject.egress_cost_per_gb === 0 ? "free" : `${formatUsd(subject.egress_cost_per_gb, 2)}/GB`}) for pulling data/weights out`);
  } else if (subject.egress_cost_per_gb > other.egress_cost_per_gb) {
    cons.push(`Pricier egress (${formatUsd(subject.egress_cost_per_gb, 2)}/GB) than ${other.name}`);
  }

  if (subject.rating > other.rating) {
    pros.push(`Higher user rating (${subject.rating.toFixed(1)} vs ${other.rating.toFixed(1)})`);
  } else if (subject.rating < other.rating) {
    cons.push(`Lower user rating (${subject.rating.toFixed(1)} vs ${other.rating.toFixed(1)})`);
  }

  if (subject.regions.length > other.regions.length) {
    pros.push(`More region choices (${subject.regions.length} vs ${other.regions.length})`);
  }

  if (pros.length === 0) pros.push(`Solid choice if you're already using ${subject.name}'s ecosystem/tooling`);
  if (cons.length === 0) cons.push("No major drawback versus the alternative — pick based on region/hardware fit");

  return { pros, cons };
}

// ---------------------------------------------------------------------------
// FAQ (3 questions, either comparison type)
// ---------------------------------------------------------------------------

export function buildGpuComparisonFaq(a: GPU, b: GPU, verdict: VerdictResult): FaqItem[] {
  const avgA = getAveragePriceForGpu(a.id);
  const avgB = getAveragePriceForGpu(b.id);
  const cheaper = verdict.cheaperId === a.id ? a : b;
  const pricier = cheaper.id === a.id ? b : a;
  const cheaperAvg = cheaper.id === a.id ? avgA : avgB;
  const pricierAvg = cheaper.id === a.id ? avgB : avgA;

  return [
    {
      question: `Is ${a.name} cheaper than ${b.name}?`,
      answer:
        avgA && avgB
          ? `${cheaper.name} is cheaper on average, at ${formatUsd(cheaperAvg ?? 0)}/hr versus ${formatUsd(
              pricierAvg ?? 0
            )}/hr for ${pricier.name} — a difference of roughly ${formatUsd(Math.abs((avgA ?? 0) - (avgB ?? 0)))}/hr across the providers we track.`
          : `We don't have enough live pricing data for both cards yet to say definitively — check each GPU's page for current rates.`,
    },
    {
      question: `Which is better for ${a.target_tasks[0] ?? b.target_tasks[0] ?? "AI workloads"}?`,
      answer: verdict.text,
    },
    {
      question: `Can I switch from ${a.name} to ${b.name} without code changes?`,
      answer: `In most cases yes — both are NVIDIA GPUs, so CUDA/PyTorch code runs on either without modification. The main things to check are VRAM headroom (${a.name}: ${a.vram_gb}GB vs ${b.name}: ${b.vram_gb}GB) for your batch size, and whether your training setup relies on NVLink for multi-GPU scaling.`,
    },
  ];
}

export function buildProviderComparisonFaq(a: Provider, b: Provider, verdict: VerdictResult): FaqItem[] {
  const minA = getMinPriceForProvider(a.slug);
  const minB = getMinPriceForProvider(b.slug);
  const cheaper = verdict.cheaperId === a.slug ? a : b;
  const pricier = cheaper.slug === a.slug ? b : a;
  const cheaperMin = cheaper.slug === a.slug ? minA : minB;
  const pricierMin = cheaper.slug === a.slug ? minB : minA;

  return [
    {
      question: `Is ${a.name} cheaper than ${b.name}?`,
      answer: `${cheaper.name} has the lower entry price, starting from ${formatUsd(cheaperMin)}/hr versus ${formatUsd(
        pricierMin
      )}/hr for ${pricier.name}. Actual savings depend on which GPU you're renting — check the shared-GPU table above for an exact comparison.`,
    },
    {
      question: `Which is better for production, long-running jobs?`,
      answer: verdict.text,
    },
    {
      question: `Does ${a.name} or ${b.name} offer better spot/interruptible pricing?`,
      answer: `${
        a.interruption_risk === "None" && b.interruption_risk !== "None"
          ? `${a.name} doesn't offer discounted spot pricing but guarantees uninterrupted instances, while ${b.name} does offer cheaper interruptible rates with ${b.interruption_risk.toLowerCase()} interruption risk.`
          : b.interruption_risk === "None" && a.interruption_risk !== "None"
          ? `${b.name} doesn't offer discounted spot pricing but guarantees uninterrupted instances, while ${a.name} does offer cheaper interruptible rates with ${a.interruption_risk.toLowerCase()} interruption risk.`
          : `Both providers carry some interruption risk on discounted instances — ${a.name} is rated "${a.interruption_risk.toLowerCase()}" and ${b.name} is rated "${b.interruption_risk.toLowerCase()}". Pick the lower-risk one for jobs without checkpointing.`
      }`,
    },
  ];
}
