//! Multimodal Perception Fusion in Rust (Vision Hash + DOM Elements + Network Telemetry).

use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

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
            // Extract inputs
            if let Ok(input_re) = Regex::new(r#"(?i)<input[^>]*name=["']([^"']+)["'][^>]*>"#) {
                for (idx, cap) in input_re.captures_iter(html).enumerate() {
                    let name = &cap[1];
                    controls.push(InteractiveControl {
                        control_id: format!("input-{}", idx),
                        tag: "input".to_string(),
                        role: "textbox".to_string(),
                        label: name.to_string(),
                        selector: format!("input[name='{}']", name),
                    });
                }
            }

            // Extract buttons
            if let Ok(btn_re) = Regex::new(r#"(?i)<button[^>]*>(.*?)</button>"#) {
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
            }

            // Extract text snippets
            if let Ok(text_re) = Regex::new(r#">([^<]{4,})<"#) {
                for cap in text_re.captures_iter(html).take(20) {
                    let snippet = cap[1].trim();
                    if !snippet.is_empty() {
                        visible_text.push(snippet.to_string());
                    }
                }
            }
        }

        let combined_text = format!("{} {} {:?}", url, title, visible_text).to_lowercase();
        let page_state = if combined_text.contains("login") || combined_text.contains("password") {
            "login".to_string()
        } else if combined_text.contains("forbidden") || combined_text.contains("403") {
            "access_denied".to_string()
        } else if combined_text.contains("admin") {
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
        assert_eq!(state.controls.len(), 3); // 2 inputs + 1 button
        assert_eq!(state.screenshot_hash.len(), 64);
    }
}
