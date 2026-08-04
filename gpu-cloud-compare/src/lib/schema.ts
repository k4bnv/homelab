import type { ComputedOffer, FaqItem, GPU } from "@/types";
import { canonicalUrl } from "@/lib/seo";

/**
 * Schema.org JSON-LD builders. Each function returns a plain object ready
 * to be dropped into `<script type="application/ld+json">` via
 * `JSON.stringify` — see `src/components/JsonLd.astro`.
 */

export interface BreadcrumbCrumb {
  name: string;
  path: string;
}

export function breadcrumbSchema(crumbs: BreadcrumbCrumb[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: canonicalUrl(crumb.path),
    })),
  };
}

export function faqSchema(faqs: FaqItem[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };
}

/**
 * Product + AggregateOffer + AggregateRating schema for a GPU detail page.
 * `offers` is a plain `AggregateOffer` (lowPrice/highPrice/offerCount) —
 * schema.org doesn't define a per-seller `offers` list nested inside
 * AggregateOffer, so we keep this strictly to the documented properties.
 * Rating is a review-count-weighted average across all providers renting it.
 */
export function gpuProductSchema(gpu: GPU, offers: ComputedOffer[]) {
  if (offers.length === 0) return null;

  const totalReviews = offers.reduce((sum, o) => sum + o.review_count, 0);
  const weightedRating =
    offers.reduce((sum, o) => sum + o.rating * o.review_count, 0) / totalReviews;

  const prices = offers.map((o) => o.price_on_demand);

  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: `${gpu.name} Cloud Rental`,
    description: gpu.description,
    brand: {
      "@type": "Brand",
      name: gpu.vendor,
    },
    aggregateRating: {
      "@type": "AggregateRating",
      ratingValue: Number(weightedRating.toFixed(2)),
      reviewCount: totalReviews,
      bestRating: 5,
      worstRating: 1,
    },
    offers: {
      "@type": "AggregateOffer",
      priceCurrency: "USD",
      lowPrice: Math.min(...prices),
      highPrice: Math.max(...prices),
      offerCount: offers.length,
    },
  };
}
