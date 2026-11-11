# Publishing AutoGrad to CIB-UC

Target repository: [CIB-UC/Gradients-PyCoilGen](https://github.com/CIB-UC/Gradients-PyCoilGen).
The first application version was published on October 24, 2026 as `01c8408`.
The AutoGrad rename and subsequent output-language changes are prepared locally
and require renewed maintainer approval before upload.

## Prepared state

- `origin` retains the original development repository.
- `cib-uc` points to the publication repository.
- `release/github-ready` holds the current application, engine changes, tests,
  reusable inputs and reviewed documentation.
- Updates descend from the published `main`, preserving its history and allowing
  a normal push.
- The active working branch and staging index are preserved. Publication is
  assembled with a separate index.

The snapshot excludes environments, generated results, local experiments,
duplicate archives, retired scripts and machine-recovery notes. Those files
remain on disk. The older development history containing simulation output is
not an ancestor of the publication branch and is not sent when pushing this ref.

## Review and upload

Review the prepared branch without changing the active working branch:

```powershell
git remote -v
git log --oneline cib-uc/main..release/github-ready
git diff --stat cib-uc/main..release/github-ready
git ls-tree -r --name-only release/github-ready
```

After maintainer approval, publish to `main`:

```powershell
git fetch cib-uc main
git push --dry-run cib-uc release/github-ready:main
git push cib-uc release/github-ready:main
```

The last command updates GitHub using the collaborator's authenticated account.
If `main` is protected, publish the branch and open a pull request instead:

```powershell
git push -u cib-uc release/github-ready
```

If someone updates `main` after preparation, preserve their work and review/update
the branch before retrying. Do not force the push or publish all local branches.
The prepared ref is a snapshot: later working-file edits are not included
automatically and must be reviewed before upload.

## Distribution checks

The baseline source copy passed 475 tests on Windows/Python 3.11.9. The AutoGrad
rename passed 41 existing GUI tests, bilingual live-window checks, launcher
setup-only verification and both CLI help commands. Output localization then
passed **491 tests** in a clean source copy, with two historical deprecation
warnings and no failures or skips.

Preparation also checks local Markdown links, required `.gitignore` exceptions,
file sizes, excluded local material and author/committer identity. A clean
extracted source copy checks for accidental dependencies on ignored files, using
the existing environment; it does not replace installation on another computer.

After upload, clone into a new folder and follow the [quick start](../README.md).
That clone uses the CIB-UC repository as `origin` and contains no excluded local
development material.
