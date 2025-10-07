from gemini_client import probe_model_availability
import os


def main():
    env = os.getenv('GEMINI_MODEL_CANDIDATES', '')
    if env:
        model_names = [m.strip() for m in env.split(',') if m.strip()]
    else:
        model_names = [
            'gemini-2.5-flash',
            'gemini-2.5-flash-preview',
            'gemini-2.5-flash-lite',
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
            'gemini-2.0-flash-001',
        ]

    print('Probing Gemini model availability...')
    for m in model_names:
        ok, reason = probe_model_availability(m, timeout=5.0)
        status = 'OK' if ok else 'NOT AVAILABLE'
        print(f'{m}: {status} - {reason}')


if __name__ == '__main__':
    main()
