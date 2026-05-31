// Hide the console window on Windows when running in release mode.
#![cfg_attr(all(not(debug_assertions), target_os = "windows"), windows_subsystem = "windows")]

fn main() {
    mp3_to_nbs_lib::run();
}
