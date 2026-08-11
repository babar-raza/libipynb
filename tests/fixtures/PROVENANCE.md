# Test Fixture Provenance

## valid/

| Fixture | Origin | License |
|---------|--------|---------|
| `minimal.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `code-and-markdown.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `with-outputs.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `empty-notebook.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `nbformat-4-{0..4}.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `rich-mime-outputs.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `with-attachments.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `r-kernel.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `with-error-output.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `with-widgets.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `large-source-cell.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `unicode-content.ipynb` | Synthetic (libipynb project) | Apache-2.0 |

## invalid/

| Fixture | Origin | License |
|---------|--------|---------|
| `missing-nbformat.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `missing-cells.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `wrong-nbformat-version.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `null-cells.ipynb` | Synthetic (libipynb project) | Apache-2.0 |

## adversarial/

| Fixture | Origin | License |
|---------|--------|---------|
| `deeply-nested-metadata.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `huge-base64-output.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `truncated-json.ipynb` | Synthetic (libipynb project) | Apache-2.0 |

## corpus/

| Fixture | Origin | License |
|---------|--------|---------|
| `spec-v45-complete.ipynb` | Synthetic, follows nbformat 4.5 spec | Apache-2.0 |
| `data-science-pattern.ipynb` | Synthetic, typical data science layout | Apache-2.0 |
| `multi-output-types.ipynb` | Synthetic, multiple output types | Apache-2.0 |
