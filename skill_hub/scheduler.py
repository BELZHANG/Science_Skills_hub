import asyncio


async def scheduler(service):
    service.schedule_due("startup")
    while True:
        await asyncio.sleep(60)
        service.schedule_due()
