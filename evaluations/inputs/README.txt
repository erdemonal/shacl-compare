Small evaluator-authored fixtures used by prepare_evaluations.py for clean-checkout
reconstruction of cases 04 and 05.

04_G0.ttl / 04_GA.ttl — evaluator-normalized data graphs for case 04
  (RDF-isomorphic to the pinned DCAT-AP-LU invalid-title fixture + title repair).

05_GA.ttl — evaluator intervention on the GeoDCAT-AP free-text multi-rights
  fragment (detach INSPIRE dct:rights from the Distribution).

These are not upstream maintainer patches. Large upstream shapes/HTML are
fetched by prepare_evaluations.py with pinned SHA-256 verification.
