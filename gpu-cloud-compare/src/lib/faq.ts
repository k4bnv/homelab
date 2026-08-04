import type { ComputedOffer, FaqItem, GPU } from "@/types";
import { formatUsd } from "@/lib/data";

/**
 * Templated FAQ generator for GPU detail pages — this is the pSEO lever:
 * every `/gpu/[slug]` page gets unique, data-driven FAQ copy (and matching
 * FAQPage JSON-LD) without hand-writing content per card.
 */
export function buildGpuFaq(gpu: GPU, offers: ComputedOffer[]): FaqItem[] {
  if (offers.length === 0) {
    return [
      {
        question: `How much does it cost to rent an ${gpu.name}?`,
        answer: `We don't have live pricing for ${gpu.name} yet — check back soon or compare similar cards on the homepage.`,
      },
    ];
  }

  const cheapest = [...offers].sort((a, b) => a.price_on_demand - b.price_on_demand)[0];
  const spotOffers = offers.filter((o) => o.price_spot !== null);
  const cheapestSpot = spotOffers.length
    ? [...spotOffers].sort((a, b) => (a.price_spot ?? 0) - (b.price_spot ?? 0))[0]
    : null;
  const priceRange = {
    min: Math.min(...offers.map((o) => o.price_on_demand)),
    max: Math.max(...offers.map((o) => o.price_on_demand)),
  };

  const faqs: FaqItem[] = [
    {
      question: `What is the cheapest place to rent an ${gpu.name}?`,
      answer: `${cheapest.name} currently has the lowest on-demand price for the ${gpu.name} at ${formatUsd(
        cheapest.price_on_demand
      )}/hr. Prices across the ${offers.length} providers we track range from ${formatUsd(
        priceRange.min
      )}/hr to ${formatUsd(priceRange.max)}/hr, so it's worth comparing before you commit to a long job.`,
    },
    {
      question: `How much VRAM does the ${gpu.name} have?`,
      answer: `The ${gpu.name} ships with ${gpu.vram_gb}GB of ${gpu.vram_type} memory, built on the ${gpu.architecture} architecture.`,
    },
    {
      question: `What is the ${gpu.name} best used for?`,
      answer: `${gpu.name} is most commonly rented for ${gpu.target_tasks
        .slice(0, 3)
        .join(", ")}. ${gpu.description}`,
    },
  ];

  if (cheapestSpot) {
    faqs.push({
      question: `Can I rent an ${gpu.name} on a spot/interruptible instance?`,
      answer: `Yes — ${cheapestSpot.name} offers spot pricing for the ${gpu.name} starting at ${formatUsd(
        cheapestSpot.price_spot ?? 0
      )}/hr, roughly ${Math.round(
        (1 - (cheapestSpot.price_spot ?? 0) / cheapestSpot.price_on_demand) * 100
      )}% cheaper than on-demand. Spot instances can be reclaimed with little notice, so they're best for fault-tolerant jobs with checkpointing.`,
    });
  }

  faqs.push({
    question: `Are there hidden costs when renting an ${gpu.name}?`,
    answer: `Beyond the hourly compute rate, watch for persistent storage (${formatUsd(
      Math.min(...offers.map((o) => o.storage_cost_per_gb)),
      2
    )}-${formatUsd(
      Math.max(...offers.map((o) => o.storage_cost_per_gb)),
      2
    )}/GB/month depending on provider) and egress/bandwidth fees for downloading model weights or datasets out of the provider's network.`,
  });

  return faqs;
}
