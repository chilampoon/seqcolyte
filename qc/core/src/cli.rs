use clap::Parser;

/// Seqcolyte QC compute core. Streams a FASTQ pair and emits `{profile, findings, eval}` JSON
/// on stdout (matching `python -m qc` field-for-field). Logs/errors go to stderr.
#[derive(Parser)]
#[command(name = "qc-core", version, about)]
pub struct Args {
    /// Consolidated spec JSON (e.g. spec/tenx_3p_v3.json)
    #[arg(long)]
    pub spec: String,

    /// R1 FASTQ (.fastq / .fastq.gz)
    #[arg(long)]
    pub r1: String,

    /// R2 FASTQ (.fastq / .fastq.gz)
    #[arg(long)]
    pub r2: String,

    /// Cell-barcode whitelist (.txt / .txt.gz); enables the whitelist check
    #[arg(long)]
    pub whitelist: Option<String>,

    /// Ground-truth labels TSV; enables the eval block
    #[arg(long)]
    pub labels: Option<String>,

    /// Cap the number of read pairs processed
    #[arg(long)]
    pub max_reads: Option<u64>,
}
