# ⚠️ WARNING — READ THIS BEFORE YOU DEPLOY ANYTHING ⚠️

> **This repository deploys an EC2 instance that runs an autonomous LLM agent
> (Kiro CLI) which, in its `admin_access=true` configuration, holds
> `AdministratorAccess` over your entire AWS account.** That means a language
> model gets a shell, the AWS CLI/SDKs, and a credential that can create,
> modify, and delete *any* resource in the account — with no human in the loop
> once you let it run unattended.
>
> If that sentence did not make you nervous, read it again.

This is the "YOLO mode" / unattended-agent configuration. The sections below
spell out exactly what you are signing up for.

---

## What "the bot takes over" actually means

When you deploy with `-c admin_access=true`, the instance profile carries the
AWS-managed `AdministratorAccess` policy. The Kiro CLI agent running on that
host can therefore, on its own initiative and without asking you:

- Launch any number of EC2 instances, GPU fleets, and spot/on-demand capacity
  in any region.
- Create, read, modify, and **delete** every resource in the account — S3
  buckets, databases, VPCs, IAM users/roles/policies, KMS keys, backups.
- Create *new* IAM principals and credentials, i.e. **escalate and persist its
  own access** beyond the instance role.
- Call paid APIs (Bedrock, SageMaker, data transfer, etc.) at machine speed.
- Disable or delete the very guardrails (budgets, CloudTrail, Config) you were
  counting on to catch it.

This is not a hypothetical "misuse" scenario. It is the *designed* capability
of the admin configuration. An LLM is a stochastic system: it can hallucinate,
loop, misinterpret an instruction, or follow adversarial content it reads off
the internet, and then faithfully execute that mistake against your account at
API speed. Think of it as the robot sent back to hunt John Connor — relentless,
literal, and tireless. The whole point of the metaphor is that it does not stop
on its own.

## 💸 The financial risk is UNLIMITED

There is **no cap** on what this can cost you. With administrator access and
the ability to spin up compute, an agent that loops, misfires, or is
manipulated can run up an effectively unbounded AWS bill — thousands of dollars
per hour is achievable with a handful of large instances or a runaway
API/data-transfer loop, and it can do it faster than you will notice.

- AWS Budgets and Cost Explorer are **lagging and best-effort**. They do not
  stop spend; they notify you after the fact, often hours late.
- An admin-capable agent can **delete or disable your budget alarms**, so even
  that late warning is not guaranteed.
- **You must watch cost continuously during any run.** Keep Cost Explorer /
  the Billing console open, set the lowest-latency alerts you can, and be ready
  to kill the instance and revoke credentials the moment something looks wrong.

## 🌍 The real-world risk is unlimited too

Beyond money: an agent with admin can delete production data, leak secrets,
expose resources publicly, mine cryptocurrency, attack third parties from your
account, or otherwise do real, irreversible harm to you and others. Some of
that is not undoable with a `cdk destroy`.

---

## ✅ MITIGATIONS — do ALL of these, every time

Treat the following as mandatory, not optional:

1. **Run only in a cost-controlled account.** Use an account that has strict
   budgets, billing alerts, and (ideally) a service control policy / spend
   ceiling attached from the organization level, where the agent cannot remove
   them.

2. **Run with FULL account isolation.** The account must contain **nothing**
   except what the bot itself creates. No production workloads, no shared data,
   no other teams' resources, no long-lived secrets, no cross-account trust
   that reaches anything you care about. The blast radius must be the account
   and nothing beyond it.

3. **USE ONLY FOR EXPERIMENTS.** This is throwaway, experimental tooling. The
   *output* of this repo — the CDK, Terraform, management scripts, and whatever
   the agent produces — belongs in **git**. The **AWS account itself is never a
   long-term home** for anything. Push the useful artifacts to a repository;
   do not leave state living in the account.

4. **Use a disposable account and destroy it when done.** Spin up a dedicated
   account with **AWS Control Tower Account Factory**, run your experiment in
   it, push the useful output to git, and then **close/delete that account**.
   Alternatively (or additionally), tear the account's contents down with a
   tool like [`aws-nuke`](https://github.com/ekristen/aws-nuke) once the
   valuable output has been committed. Never reuse the experiment account for
   anything that matters.

5. **Watch cost the entire time it runs.** See the financial section above.
   Do not start an unattended run you are not actively monitoring.

6. **Prefer the SSM-only (non-admin) role whenever you can.** Deploy *without*
   `admin_access=true` unless the experiment genuinely requires it. The
   least-privilege path is the default for a reason.

---

## Acknowledgement of risk

By deploying this stack — and especially by passing `-c admin_access=true` —
**you assume all risk.** You accept that:

- You are giving an autonomous LLM broad, up to full-administrator, control of
  an AWS account.
- The financial exposure is **unlimited** and is **entirely your
  responsibility**.
- The authors and contributors of this repository are **not responsible for
  your AWS bill**, for any data loss, for any security incident, or for any
  other consequence of running it — up to and including, metaphorically
  speaking, ending the world as we know it.
- You have watched at least Terminator 1 and Terminator 2 to understand
  the risk of giving an AI the resources of AWS. Seriously this is only
  for senior engineers who understand what they are doing. DO NOT USE
  IF YOU ARE A VIBE CODER.

If you are not willing to own every one of those outcomes, **do not deploy
this.**
