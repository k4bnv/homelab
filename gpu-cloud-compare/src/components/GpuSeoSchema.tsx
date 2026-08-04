import { breadcrumbSchema, faqSchema, gpuProductSchema, type BreadcrumbCrumb } from "@/lib/schema";
import type { ComputedOffer, FaqItem, GPU } from "@/types";

/**
 * All JSON-LD for a `/gpu/[slug]` page in one place: `Product` (with a
 * nested `AggregateOffer` + `AggregateRating`), `BreadcrumbList`, and
 * `FAQPage`. Rendered server-side only (no `client:*` directive on the
 * caller) — this emits plain `<script>` tags, no JS ships to the browser.
 */
interface Props {
  gpu: GPU;
  offers: ComputedOffer[];
  faqs: FaqItem[];
  breadcrumbs: BreadcrumbCrumb[];
}

export default function GpuSeoSchema({ gpu, offers, faqs, breadcrumbs }: Props) {
  const schemas = [
    gpuProductSchema(gpu, offers),
    breadcrumbSchema(breadcrumbs),
    faqSchema(faqs),
  ].filter((schema): schema is NonNullable<typeof schema> => schema !== null);

  return (
    <>
      {schemas.map((schema, i) => (
        // eslint-disable-next-line react/no-danger -- JSON-LD requires raw <script> content
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
    </>
  );
}
