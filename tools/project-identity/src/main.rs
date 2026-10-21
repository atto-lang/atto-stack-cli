use std::{fs, path::Path};

fn require(condition: bool, description: &str) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(format!("project identity contract failed: {description}"))
    }
}

fn run() -> Result<(), String> {
    let readme = fs::read_to_string("README.md").map_err(|e| format!("README.md: {e}"))?;
    let bootstrap =
        fs::read_to_string("bin/oreslang-stack").map_err(|e| format!("bin/oreslang-stack: {e}"))?;
    let sources =
        fs::read_to_string("src/main.ores").map_err(|e| format!("src/main.ores: {e}"))?;

    require(
        readme.starts_with("# Oreslang Stack CLI\n"),
        "correct project heading",
    )?;
    require(
        readme.contains("## Project identity: Oreslang Stack is not ORES Stack"),
        "explicit project distinction",
    )?;
    require(
        readme.contains("https://github.com/ores-truffle-oreslang/oreslang-stack-cli"),
        "canonical Oreslang CLI URL",
    )?;
    require(
        readme.contains("https://github.com/ores-stack/ores-stack-cli"),
        "cross-reference to distinct Rust CLI",
    )?;
    require(
        readme.contains("`oreslang-stack`") && readme.contains("`ores-stack`"),
        "separate CLI commands",
    )?;
    require(
        readme.contains("**private**")
            && readme.contains("Git tree SHAs")
            && readme.contains("executed"),
        "private exact-tree CI mirror constraints",
    )?;
    require(
        readme.contains("PR #496 is merged"),
        "record merged source dependency; do not call it unmerged",
    )?;
    require(
        readme.contains("installed Java/Graal runtime"),
        "separate merged source from installed runtime compatibility",
    )?;
    require(
        readme.contains("deploy` currently fails closed"),
        "deployment must not be represented as certified",
    )?;
    require(
        !readme.contains("This PR must remain")
            && !readme.contains("Until this dependency is merged"),
        "reject stale pull request claims",
    )?;
    require(
        !readme.contains(r"|\n|"),
        "reject escaped newline breaking Markdown table",
    )?;

    let table_rows: Vec<&str> = readme
        .lines()
        .filter(|line| line.starts_with("| `"))
        .collect();
    require(
        table_rows.len() >= 7 && table_rows.iter().all(|row| row.trim_end().ends_with('|')),
        "command-table rows must be well-formed",
    )?;
    require(
        Path::new("src/main.ores").is_file() && sources.contains("oreslang-stack-cli"),
        "the Oreslang source implementation exists",
    )?;
    require(
        Path::new("bin/oreslang-stack").is_file() && bootstrap.contains("ORESLANG_BIN"),
        "the POSIX runtime bootstrap exists",
    )?;
    require(
        !Path::new("Cargo.toml").exists() && !Path::new("src/main.rs").exists(),
        "Rust CLI must not be misidentified as this repository",
    )?;

    println!("Oreslang Stack identity documentation contract passed (static only)");
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::require;

    #[test]
    fn require_fails_closed() {
        assert!(require(true, "ok").is_ok());
        assert_eq!(
            require(false, "missing").unwrap_err(),
            "project identity contract failed: missing"
        );
    }
}
