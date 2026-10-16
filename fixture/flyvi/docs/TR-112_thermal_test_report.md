# TR-112: Thermal derating test, PSM-28 Rev 2 regulator candidates

Synthetic document. Flyvi Technologies Pvt. Ltd., Quality Lab.
Prepared by: Raghavendra. Reviewed by: Satish. Date: 2025-03-10.

--- Page 1 ---

## Purpose

Compare NB54360 (current) and NB54361-L (proposed cost-down) on PSM-28 Rev 2 under the TP-PSM-07 thermal and load qualification procedure.

--- Page 2 ---

## Setup

Sealed enclosure representative of a PDU-28 avionics-bay installation, no forced air. Full load 3 A on the 3.3 V rail. Ambient stepped from 40C to 70C in 5C steps, 2 hours per step.

--- Page 3 ---

## Measurements

Case temperature, output ripple, and regulation were logged at each step for both candidates.

--- Page 4 ---

## Results

| Candidate | Max ambient with regulation held | Failure mode |
|---|---|---|
| NB54360 | 70C (test limit), 11C junction margin | None |
| NB54361-L | 65C | Thermal shutdown at 68C ambient |

Conclusion: NB54361-L does not meet the 70C ambient requirement for sealed avionics installations. NB54360 passes.

--- Page 5 ---

## Applicability

Results apply to PSM-28 Rev 2 as used in PDU-28 and BCU-24.
