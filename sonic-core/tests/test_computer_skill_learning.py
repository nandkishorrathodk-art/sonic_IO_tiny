from sonic.computer_use.skill_ledger import ComputerSkillLedger


def test_skill_ledger_persists_verified_success_and_failure(tmp_path):
    first = ComputerSkillLedger("tenant-a", root=str(tmp_path))
    first.record_success("editor", "GUI_CLICK", "controls changed")
    first.record_failure("editor", "GUI_TYPE", "target disappeared")

    second = ComputerSkillLedger("tenant-a", root=str(tmp_path))
    context = second.context()
    assert "verified actions: GUI_CLICK" in context
    assert "avoid GUI_TYPE" in context


def test_skill_ledger_is_tenant_scoped(tmp_path):
    first = ComputerSkillLedger("tenant-a", root=str(tmp_path))
    first.record_success("app", "GUI_CLICK", "real transition")

    other = ComputerSkillLedger("tenant-b", root=str(tmp_path))
    assert other.context() == ""
