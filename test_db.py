import asyncio
from linkedin_bot.db.session import init_db
from linkedin_bot.db.repository import ApplicationRepository

async def test():
    await init_db()
    # Add a dummy record
    await ApplicationRepository.add_record(
        job_id="job123",
        title="Test Title",
        company="Company X",
        location="Earth",
        url="http",
        match_score=90,
        status="dry_run",
        reason=""
    )
    stats = await ApplicationRepository.get_stats()
    records = await ApplicationRepository.get_applied_job_ids()
    print("Stats:", stats)
    print("Records:", records)

if __name__ == "__main__":
    asyncio.run(test())
