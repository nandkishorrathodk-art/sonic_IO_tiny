//! Multimodal Perception Fusion in Rust (Vision Hash + DOM Elements + Network Telemetry).
//!
//! Uses static OnceLock regexes for zero-allocation, microsecond-speed DOM element parsing.

use std::sync::OnceLock;
use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

static INPUT_RE: OnceLock<Regex> = OnceLock::new();
static BUTTON_RE: OnceLock<Regex> = OnceLock::new();
static A_RE: OnceLock<Regex> = OnceLock::new();
static FORM_RE: OnceLock<Regex> = OnceLock::new();
static TEXTAREA_RE: OnceLock<Regex> = OnceLock::new();
static SELECT_RE: OnceLock<Regex> = OnceLock::new();
static TEXT_RE: OnceLock<Regex> = OnceLock::new();

fn get_input_re() -> &'static Regex {
    INPUT_RE.get_or_init(|| Regex::new(r#"(?i)<input[^>]*?(?:name=["']([^"']+)["']|id=["']([^"']+)["']|placeholder=["']([^"']+)["'])[^>]*>"#).unwrap())
}

fn get_button_re() -> &'static Regex {
    BUTTON_RE.get_or_init(|| Regex::new(r#"(?i)<button[^>]*>(.*?)</button>"#).unwrap())
}

fn get_a_re() -> &'static Regex {
    A_RE.get_or_init(|| Regex::new(r#"(?i)<a[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>"#).unwrap())
}

fn get_form_re() -> &'static Regex {
    FORM_RE.get_or_init(|| Regex::new(r#"(?i)<form[^>]*action=["']([^"']+)["'][^>]*>"#).unwrap())
}

fn get_textarea_re() -> &'static Regex {
    TEXTAREA_RE.get_or_init(|| Regex::new(r#"(?i)<textarea[^>]*?(?:name=["']([^"']+)["']|id=["']([^"']+)["'])[^>]*>"#).unwrap())
}

fn get_select_re() -> &'static Regex {
    SELECT_RE.get_or_init(|| Regex::new(r#"(?i)<select[^>]*?(?:name=["']([^"']+)["']|id=["']([^"']+)["'])[^>]*>"#).unwrap())
}

fn get_text_re() -> &'static Regex {
    TEXT_RE.get_or_init(|| Regex::new(r#">([^<]{4,})<"#).unwrap())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InteractiveControl {
    pub control_id: String,
    pub tag: String,
    pub role: String,
    pub label: String,
    pub selector: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuredWorldState {
    pub url: String,
    pub title: String,
    pub page_state: String,
    pub controls: Vec<InteractiveControl>,
    pub visible_text: Vec<String>,
    pub screenshot_hash: String,
}

pub struct PerceptionFusion;

impl PerceptionFusion {
    pub fn fuse(
        url: &str,
        title: &str,
        screenshot_bytes: Option<&[u8]>,
        dom_html: Option<&str>,
    ) -> StructuredWorldState {
        let s_hash = match screenshot_bytes {
            Some(bytes) => {
                let mut hasher = Sha256::new();
                hasher.update(bytes);
                format!("{:x}", hasher.finalize())
            }
            None => String::new(),
        };

        let mut controls = Vec::new();
        let mut visible_text = Vec::new();

        if let Some(html) = dom_html {
            // 1. Extract inputs
            let input_re = get_input_re();
            for (idx, cap) in input_re.captures_iter(html).enumerate() {
                let label = cap.get(1)
                    .or_else(|| cap.get(2))
                    .or_else(|| cap.get(3))
                    .map(|m| m.as_str())
                    .unwrap_or("unnamed_input");

                controls.push(InteractiveControl {
                    control_id: format!("input-{}", idx),
                    tag: "input".to_string(),
                    role: "textbox".to_string(),
                    label: label.to_string(),
                    selector: format!("input[name='{}']", label),
                });
            }

            // 2. Extract buttons
            let btn_re = get_button_re();
            for (idx, cap) in btn_re.captures_iter(html).enumerate() {
                let text = cap[1].trim();
                controls.push(InteractiveControl {
                    control_id: format!("btn-{}", idx),
                    tag: "button".to_string(),
                    role: "button".to_string(),
                    label: text.to_string(),
                    selector: format!("button:contains('{}')", text),
                });
            }

            // 3. Extract links (<a> tags)
            let a_re = get_a_re();
            for (idx, cap) in a_re.captures_iter(html).take(25).enumerate() {
                let href = cap[1].trim();
                let text = cap[2].trim();
                let label = if !text.is_empty() { text } else { href };
                controls.push(InteractiveControl {
                    control_id: format!("link-{}", idx),
                    tag: "a".to_string(),
                    role: "link".to_string(),
                    label: label.to_string(),
                    selector: format!("a[href='{}']", href),
                });
            }

            // 4. Extract forms
            let form_re = get_form_re();
            for (idx, cap) in form_re.captures_iter(html).enumerate() {
                let action = cap[1].trim();
                controls.push(InteractiveControl {
                    control_id: format!("form-{}", idx),
                    tag: "form".to_string(),
                    role: "form".to_string(),
                    label: action.to_string(),
                    selector: format!("form[action='{}']", action),
                });
            }

            // 5. Extract textareas
            let textarea_re = get_textarea_re();
            for (idx, cap) in textarea_re.captures_iter(html).enumerate() {
                let label = cap.get(1)
                    .or_else(|| cap.get(2))
                    .map(|m| m.as_str())
                    .unwrap_or("textarea");

                controls.push(InteractiveControl {
                    control_id: format!("textarea-{}", idx),
                    tag: "textarea".to_string(),
                    role: "textbox".to_string(),
                    label: label.to_string(),
                    selector: format!("textarea[name='{}']", label),
                });
            }

            // 6. Extract selects
            let select_re = get_select_re();
            for (idx, cap) in select_re.captures_iter(html).enumerate() {
                let label = cap.get(1)
                    .or_else(|| cap.get(2))
                    .map(|m| m.as_str())
                    .unwrap_or("select");

                controls.push(InteractiveControl {
                    control_id: format!("select-{}", idx),
                    tag: "select".to_string(),
                    role: "combobox".to_string(),
                    label: label.to_string(),
                    selector: format!("select[name='{}']", label),
                });
            }

            // 7. Extract text snippets
            let text_re = get_text_re();
            for cap in text_re.captures_iter(html).take(30) {
                let snippet = cap[1].trim();
                if !snippet.is_empty() && (!snippet.contains(';') || snippet.to_lowercase().contains("flag{")) {
                    visible_text.push(snippet.to_string());
                }
            }
        }

        let raw_dom = dom_html.unwrap_or("");
        let combined_text = format!("{} {} {} {:?}", url, title, raw_dom, visible_text).to_lowercase();
        let page_state = if combined_text.contains("flag{") || combined_text.contains("ctf{") {
            "flag_captured".to_string()
        } else if combined_text.contains("login") || combined_text.contains("signin") || combined_text.contains("password") {
            "login".to_string()
        } else if combined_text.contains("forbidden") || combined_text.contains("403") || combined_text.contains("access denied") {
            "access_denied".to_string()
        } else if combined_text.contains("admin") || combined_text.contains("dashboard") {
            "admin_portal".to_string()
        } else {
            "content_page".to_string()
        };

        StructuredWorldState {
            url: url.to_string(),
            title: title.to_string(),
            page_state,
            controls,
            visible_text,
            screenshot_hash: s_hash,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_perception_fusion_extraction() {
        let html = r#"
            <html>
                <head><title>Admin Auth</title></head>
                <body>
                    <form action="/login">
                        <input name="username" />
                        <input name="password" />
                        <button>Sign In</button>
                    </form>
                    <a href="/register">Create Account</a>
                    <textarea name="feedback"></textarea>
                </body>
            </html>
        "#;

        let fake_screenshot = b"PNG_FAKE_IMAGE_BYTES";
        let state = PerceptionFusion::fuse(
            "https://app.local/login",
            "Admin Auth",
            Some(fake_screenshot),
            Some(html),
        );

        assert_eq!(state.page_state, "login");
        // 2 inputs + 1 button + 1 link + 1 form + 1 textarea = 6 controls
        assert_eq!(state.controls.len(), 6);
        assert_eq!(state.screenshot_hash.len(), 64);
    }

    #[test]
    fn test_flag_page_state_detection() {
        let html = "<html><body><h1>Congratulations!</h1><p>flag{n4t1v3_rust_k3rn3l_ftw}</p></body></html>";
        let state = PerceptionFusion::fuse(
            "https://ctf.local/challenge",
            "CTF Victory",
            None,
            Some(html),
        );
        assert_eq!(state.page_state, "flag_captured");
    }
}
