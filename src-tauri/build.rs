fn main() {
    // Fix MinGW "export ordinal too large" when linking cdylib with many symbols.
    // Passed through gcc to ld: -Wl, tells gcc to forward the flag to the linker.
    // Only affects cdylib linking — build scripts and binaries are unaffected.
    println!("cargo:rustc-cdylib-link-arg=-Wl,--exclude-libs,ALL");
    tauri_build::build()
}
