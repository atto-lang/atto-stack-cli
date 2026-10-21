use std::{fs, path::Path, process};

fn require(ok: bool, description: &str) {
    if !ok {
        eprintln!("project identity contract failed: {description}");
        process::exit(1);
    }
}

fn read(path: &str) -> String {
    fs::read_to_string(path).unwrap_or_else(|e| {
        eprintln!("project identity contract failed: cannot read {path}: {e}");
        process::exit(1);
    })
}

fn main() {
    let readme = read("README.md");
    let bootstrap = read("bin/oreslang-stack");
    let sources = read("src/main.ores");
    let tick = char::from(96);
    let oreslang_stack = format!("{tick}oreslang-stack{tick}");
    let ores_stack = format!("{tick}ores-stack{tick}");

    require(readme.starts_with("# Oreslang Stack CLI\n"), "correct project heading");
    require(readme.contains("## Project identity: Oreslang Stack is not ORES Stack"), "explicit project distinction");
    require(readme.contains("https://github.com/ores-truffle-oreslang/oreslang-stack-cli"), "canonical Oreslang CLI URL");
    require(readme.contains("https://github.com/ores-stack/ores-stack-cli"), "cross-reference to distinct Rust CLI");
    require(readme.contains(&oreslang_stack) && readme.contains(&ores_stack), "separate CLI commands");
    require(readme.contains("**private**") && readme.contains("Git tree SHAs") && readme.contains("executed"), "private exact-tree CI mirror constraints");
    require(readme.contains("PR #496 is merged"), "record merged source dependency; do not call it unmerged");
    require(readme.contains("installed Java/Graal runtime"), "separate merged source from installed runtime compatibility");
    require(readme.contains("deploy") && readme.contains("currently fails closed"), "deployment must not be represented as certified");
    require(!readme.contains("This PR must remain") && !readme.contains("Until this dependency is merged"), "reject stale pull request claims");
    require(!readme.contains(r"|\n|"), "reject escaped newline breaking Markdown table");

    let table_rows: Vec<&str> = readme.lines().filter(|row| row.starts_with("| ")).filter(|row| row.contains(&tick.to_string())).collect();
    require(table_rows.len() >= 7 && table_rows.iter().all(|row| row.trim_end().ends_with('|')), "command-table rows must be well-formed");
    require(Path::new("src/main.ores").is_file() && sources.contains("oreslang-stack-cli"), "the Oreslang source implementation exists");
    require(Path::new("bin/oreslang-stack").is_file() && bootstrap.contains("ORESLANG_BIN"), "the POSIX runtime bootstrap exists");
    require(!Path::new("Cargo.toml").exists() && !Path::new("src/main.rs").exists(), "Rust CLI must not be misidentified as this repository");

    println!("Oreslang Stack identity documentation contract passed (static only)");
}
