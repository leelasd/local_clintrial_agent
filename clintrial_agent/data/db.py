import psycopg2
from psycopg2.extras import DictCursor
import logging
from clintrial_agent.config import CONFIG

logger = logging.getLogger(__name__)

def get_db_connection():
    """Create a connection to the local PostgreSQL database."""
    dbname = CONFIG.get('db', {}).get('name', 'chembl_37')
    host = CONFIG.get('db', {}).get('host', 'localhost')
    user = CONFIG.get('db', {}).get('user', None)
    return psycopg2.connect(dbname=dbname, host=host, user=user)

def _map_phase(phase_str):
    if not phase_str:
        return ["N/A"]
    phase_upper = phase_str.upper()
    phases = []
    if "EARLY PHASE 1" in phase_upper:
        phases.append("EARLY_PHASE1")
    else:
        if "PHASE 1" in phase_upper or "PHASE I" in phase_upper:
            phases.append("PHASE1")
        if "PHASE 2" in phase_upper or "PHASE II" in phase_upper:
            phases.append("PHASE2")
        if "PHASE 3" in phase_upper or "PHASE III" in phase_upper:
            phases.append("PHASE3")
        if "PHASE 4" in phase_upper or "PHASE IV" in phase_upper:
            phases.append("PHASE4")
    return phases if phases else [phase_str]

def fetch_trial_from_db(nct_id: str) -> dict | None:
    """
    Fetch trial protocol sections from the local PostgreSQL database
    and map them to match the ClinicalTrials.gov v2 API JSON structure.
    Returns None if trial is not found.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
    except Exception as e:
        logger.warning(f"Could not connect to local database: {e}")
        return None

    try:
        # 1. Fetch study core info
        cur.execute(
            "SELECT brief_title, official_title, phase, overall_status, study_type, "
            "start_date, completion_date, primary_completion_date, enrollment, enrollment_type, "
            "has_dmc, is_fda_regulated_drug "
            "FROM ctgov.studies WHERE nct_id = %s",
            (nct_id,)
        )
        study = cur.fetchone()
        if not study:
            return None

        # 2. Fetch designs info
        cur.execute(
            "SELECT allocation, intervention_model, primary_purpose, masking "
            "FROM ctgov.designs WHERE nct_id = %s",
            (nct_id,)
        )
        design_row = cur.fetchone()
        design = design_row if design_row is not None else {}

        # 3. Fetch eligibilities info
        cur.execute(
            "SELECT gender, minimum_age, maximum_age, healthy_volunteers, criteria "
            "FROM ctgov.eligibilities WHERE nct_id = %s",
            (nct_id,)
        )
        elig_row = cur.fetchone()
        elig = elig_row if elig_row is not None else {}

        # 4. Fetch brief summary
        cur.execute(
            "SELECT description FROM ctgov.brief_summaries WHERE nct_id = %s",
            (nct_id,)
        )
        summary = cur.fetchone()
        brief_summary = (summary['description'] if summary and summary['description'] is not None else "")

        # 5. Fetch detailed description
        cur.execute(
            "SELECT description FROM ctgov.detailed_descriptions WHERE nct_id = %s",
            (nct_id,)
        )
        desc = cur.fetchone()
        detailed_desc = (desc['description'] if desc and desc['description'] is not None else "")

        # 6. Fetch design groups (arms)
        cur.execute(
            "SELECT group_type, title, description FROM ctgov.design_groups WHERE nct_id = %s",
            (nct_id,)
        )
        design_groups = []
        for row in cur.fetchall():
            design_groups.append({
                'group_type': row['group_type'] or '',
                'title': row['title'] or '',
                'description': row['description'] or ''
            })

        # 7. Fetch interventions
        cur.execute(
            "SELECT name, intervention_type, description FROM ctgov.interventions WHERE nct_id = %s",
            (nct_id,)
        )
        interventions = []
        for row in cur.fetchall():
            interventions.append({
                'name': row['name'] or '',
                'intervention_type': row['intervention_type'] or '',
                'description': row['description'] or ''
            })

        # 8. Fetch sponsors
        cur.execute(
            "SELECT name, lead_or_collaborator, agency_class FROM ctgov.sponsors WHERE nct_id = %s",
            (nct_id,)
        )
        sponsors_rows = cur.fetchall()
        lead_sponsor = {}
        collaborators = []
        for row in sponsors_rows:
            name = row['name'] or ''
            lead_or_collaborator = row['lead_or_collaborator'] or ''
            agency_class = row['agency_class'] or ''
            if lead_or_collaborator == 'lead':
                lead_sponsor = {'name': name, 'class': agency_class}
            else:
                collaborators.append({'name': name, 'agency_class': agency_class})

        # 9. Fetch design outcomes (endpoints)
        cur.execute(
            "SELECT outcome_type, measure, description, time_frame FROM ctgov.design_outcomes WHERE nct_id = %s",
            (nct_id,)
        )
        outcomes_rows = cur.fetchall()
        primary_outcomes = []
        secondary_outcomes = []
        for row in outcomes_rows:
            outcome_dict = {
                'measure': row['measure'] or '',
                'description': row['description'] or '',
                'timeFrame': row['time_frame'] or ''
            }
            outcome_type = row['outcome_type'] or ''
            if outcome_type == 'primary':
                primary_outcomes.append(outcome_dict)
            elif outcome_type == 'secondary':
                secondary_outcomes.append(outcome_dict)

        # 10. Fetch conditions
        cur.execute(
            "SELECT name FROM ctgov.conditions WHERE nct_id = %s",
            (nct_id,)
        )
        conditions = [row['name'] for row in cur.fetchall() if row['name'] is not None]

        # 11. Fetch keywords
        cur.execute(
            "SELECT name FROM ctgov.keywords WHERE nct_id = %s",
            (nct_id,)
        )
        keywords = [row['name'] for row in cur.fetchall() if row['name'] is not None]

        # Reconstruct API JSON protocolSection adapter structure
        protocol = {
            'identificationModule': {
                'briefTitle': study['brief_title'] or 'N/A',
                'officialTitle': study['official_title'] or 'N/A',
            },
            'designModule': {
                'phases': _map_phase(study['phase']),
                'enrollmentInfo': {
                    'count': study['enrollment'] or 0,
                    'type': study['enrollment_type'] or 'ESTIMATED'
                },
                'designInfo': {
                    'allocation': design.get('allocation') or 'NA',
                    'interventionModel': design.get('intervention_model') or 'SINGLE_GROUP',
                    'primaryPurpose': design.get('primary_purpose') or 'TREATMENT',
                    'maskingInfo': {
                        'masking': design.get('masking') or 'NONE'
                    }
                }
            },
            'descriptionModule': {
                'briefSummary': brief_summary,
                'detailedDescription': detailed_desc
            },
            'eligibilityModule': {
                'sex': elig.get('gender') or 'ALL',
                'minimumAge': elig.get('minimum_age') or 'N/A',
                'maximumAge': elig.get('maximum_age') or 'N/A',
                'healthyVolunteers': bool(elig.get('healthy_volunteers')),
                'eligibilityCriteria': elig.get('criteria') or ''
            },
            'armsInterventionsModule': {
                'armGroups': design_groups,
                'interventions': interventions
            },
            'sponsorCollaboratorsModule': {
                'leadSponsor': lead_sponsor,
                'collaborators': collaborators
            },
            'outcomesModule': {
                'primaryOutcomes': primary_outcomes,
                'secondaryOutcomes': secondary_outcomes
            },
            'conditionModule': {
                'conditions': conditions
            },
            'keywordsModule': {
                'keywords': keywords
            }
        }

        # Add has_dmc and is_fda_regulated_drug details
        protocol['designModule']['hasDmc'] = bool(study['has_dmc'])
        protocol['designModule']['isFdaRegulatedDrug'] = bool(study['is_fda_regulated_drug'])

        return protocol

    except Exception as e:
        logger.error(f"Error executing database queries for {nct_id}: {e}")
        return None
    finally:
        cur.close()
        conn.close()
