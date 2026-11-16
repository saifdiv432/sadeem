#!/usr/bin/env python3
"""
Upload Sadeem ISO and SHA256SUMS to Hugging Face dataset repository.
"""
import os
import sys
from huggingface_hub import HfApi, create_repo

def main():
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("::error::HF_TOKEN secret is not set! Please add HF_TOKEN to your repository secrets.", file=sys.stderr)
        sys.exit(1)

    api = HfApi(token=token)
    try:
        user_info = api.whoami()
    except Exception as e:
        print(f"::error::Failed to authenticate with Hugging Face API: {e}", file=sys.stderr)
        sys.exit(1)

    username = user_info.get("name") or user_info.get("username")
    if not username:
        print("::error::Unable to determine Hugging Face username from token.", file=sys.stderr)
        sys.exit(1)

    repo_id = f"{username}/sadeem-iso"
    print(f"Authenticated as Hugging Face user: {username}")
    print(f"Target dataset repository: {repo_id}")

    print("Ensuring public dataset repository exists...")
    create_repo(
        repo_id=repo_id,
        repo_type="dataset",
        exist_ok=True,
        private=False,
        token=token
    )

    build_dir = "build-output"
    iso_file = os.path.join(build_dir, "sadeem-45.iso")
    checksum_file = os.path.join(build_dir, "SHA256SUMS")

    if not os.path.exists(iso_file):
        candidates = [f for f in os.listdir(build_dir) if f.endswith(".iso")]
        if candidates:
            iso_file = os.path.join(build_dir, candidates[0])
        else:
            print(f"::error::No ISO file found in {build_dir}", file=sys.stderr)
            sys.exit(1)

    print(f"Uploading {iso_file} to {repo_id} (sadeem-45.iso)...")
    api.upload_file(
        path_or_fileobj=iso_file,
        path_in_repo="sadeem-45.iso",
        repo_id=repo_id,
        repo_type="dataset"
    )
    print("ISO uploaded successfully!")

    if os.path.exists(checksum_file):
        print(f"Uploading {checksum_file} to {repo_id}...")
        api.upload_file(
            path_or_fileobj=checksum_file,
            path_in_repo="SHA256SUMS",
            repo_id=repo_id,
            repo_type="dataset"
        )
        print("SHA256SUMS uploaded successfully!")

    direct_url = f"https://huggingface.co/datasets/{username}/sadeem-iso/resolve/main/sadeem-45.iso"
    print(f"Direct download URL: {direct_url}")

    # Export to GITHUB_ENV for subsequent workflow steps
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"DIRECT_URL={direct_url}\n")
            f.write(f"HF_REPO={repo_id}\n")
            f.write(f"HF_USERNAME={username}\n")

if __name__ == "__main__":
    main()
