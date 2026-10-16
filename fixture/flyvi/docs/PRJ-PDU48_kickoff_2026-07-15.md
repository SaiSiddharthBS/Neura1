# PDU-48 kickoff, 2026-07-15

Synthetic meeting notes. Attendees: Vishwas, Raghavendra, Sai, Satish.

- Vishwas: PDU-48 adds a second Ethernet port and a redesigned power stage. Target release June 2027. PDU-28 Rev D is the stepping stone and stays a draft until the power stage settles.
- Raghavendra: the power stage must keep PSM-28's 70C sealed-enclosure rating. I will look at MX-3360 as a second source for the 3.3 V rail so we are not single-sourced on NB54360 again.
- Sai: any new regulator means re-tuning pmic_seq.c power-good timing. Budget a week of firmware work per candidate.
- Satish: every candidate goes through TP-PSM-07, including the new cold-start step.
- Decision owner for the power stage: Raghavendra. Final approval: Vishwas.
