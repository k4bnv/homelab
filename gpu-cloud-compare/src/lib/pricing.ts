/** Base persistent disk size assumed by the cost calculator, in GB. */
export const BASE_DISK_GB = 100;

export interface CostBreakdownRow {
  label: string;
  hours: number;
  computeCost: number;
  storageCost: number;
  totalCost: number;
}

const PERIODS: { label: string; days: number }[] = [
  { label: "24 Hours", days: 1 },
  { label: "7 Days", days: 7 },
  { label: "30 Days", days: 30 },
];

/**
 * Total cost of ownership for a given hourly rate + monthly storage rate,
 * assuming a constant `BASE_DISK_GB` persistent disk is attached for the
 * whole period (storage cost is prorated by days/30).
 */
export function buildCostBreakdown(
  pricePerHour: number,
  storageCostPerGbMonth: number
): CostBreakdownRow[] {
  return PERIODS.map(({ label, days }) => {
    const hours = days * 24;
    const computeCost = pricePerHour * hours;
    const storageCost = storageCostPerGbMonth * BASE_DISK_GB * (days / 30);
    return {
      label,
      hours,
      computeCost,
      storageCost,
      totalCost: computeCost + storageCost,
    };
  });
}
