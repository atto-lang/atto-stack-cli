use std::env;
use std::process;

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    match oreslang_stack_cli::execute(&args) {
        Ok(output) => println!("{output}"),
        Err(message) => {
            eprintln!("oreslang-stack: {message}");
            process::exit(1);
        }
    }
}
