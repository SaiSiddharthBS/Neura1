# VC-300 kickoff, 2026-07-15

Synthetic meeting notes. Attendees: Arjun Mehta, Priya Nair, Rahul Iyer, Ananya Rao.

- Arjun: VC-300 adds a second Ethernet port and a redesigned power stage. Target release June 2027. VC-200 Rev D is the stepping stone and stays a draft until the power stage settles.
- Priya: the power stage must keep PSU-24's 70C sealed-cabinet rating. I will look at MX-3360 as a second source for the 3.3 V rail so we are not single-sourced on NB54360 again.
- Rahul: any new regulator means re-tuning pmic_seq.c power-good timing. Budget a week of firmware work per candidate.
- Ananya: every candidate goes through TP-PSU-07, including the new cold-start step.
- Decision owner for the power stage: Priya Nair. Final approval: Arjun Mehta.
