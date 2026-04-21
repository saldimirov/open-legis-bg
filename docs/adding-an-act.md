# Adding an act

1. Scaffold:

        uv run open-legis new-fixture \
          --type zakon --slug my-slug --year 2025 \
          --date 2025-01-01 --title "Full Bulgarian title" \
          --dv-broy 12

2. Edit the generated `fixtures/akn/.../*.bul.xml`:

   - Replace the TODO body with your authored AKN (`<part>`, `<chapter>`,
     `<article>`, `<paragraph>`, `<point>`, `<letter>`).
   - Each structural element must carry a unique `eId` following AKN
     conventions (`art_1`, `art_1__para_1`, etc.).
   - Use real wording from the ДВ promulgation PDF. Do not copy from
     lex.bg or other consolidated databases (see `takedown.md` and the
     legal policy in the design spec).

3. Cite the consolidation baseline in your commit message, e.g.:

        fixtures: НК as in force 2024-01-01

        Consolidated through ДВ бр. 84/2023.

4. Validate locally:

        uv run open-legis load fixtures/akn
        uv run pytest

5. Open a PR.
