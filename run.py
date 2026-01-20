<<<<<<< HEAD
#!/usr/bin/env python3
"""
Simple script to run the Data Warehouse API
"""
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info"
    )
=======
#!/usr/bin/env python3
"""
Simple script to run the Data Warehouse API
"""
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info"
    )
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
