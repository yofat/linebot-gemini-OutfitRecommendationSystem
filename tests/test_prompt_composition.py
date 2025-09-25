import prompts


def test_system_rules_and_context():
    scene = '上班'
    purpose = '正式'
    time_weather = '傍晚 微熱'
    user_ctx = prompts.USER_CONTEXT_TEMPLATE.format(scene=scene, purpose=purpose, time_weather=time_weather)
    assert '<<USER_CONTEXT>>' in user_ctx and '<</USER_CONTEXT>>' in user_ctx
    assert prompts.SYSTEM_RULES.startswith('請遵守系統規則')
    assert prompts.TASK_INSTRUCTION.startswith('你是一個穿搭評分')
