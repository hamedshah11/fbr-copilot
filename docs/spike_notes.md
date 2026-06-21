# Spike notes

Throwaway exploration log. Each spike appends a dated, per-step record of which
locator strategy worked and where the IRIS page was ambiguous enough to need a
vision fallback. Findings here get distilled into `config/iris_map/*.yaml`.

Format per step:

```
[step] <what> — selector: <role|label|text|css|fallback> — status: ok|flaky|fallback
  note: <what was ambiguous / what to confirm>
```

<!-- spike runs append below -->
